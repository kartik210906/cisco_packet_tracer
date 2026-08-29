"""Deterministic Cisco/Packet Tracer evidence checker.

The checker never calls the AI.  It is intentionally conservative: it reports
ISSUE_FOUND only when the supplied evidence is sufficient to prove a fault,
NO_ISSUE_FOUND when it can positively verify a healthy condition, and
UNVERIFIED otherwise.
"""

import re
from collections import Counter
from ipaddress import ip_address, ip_interface, ip_network

STATUS_ISSUE = "ISSUE_FOUND"
STATUS_NONE = "NO_ISSUE_FOUND"
STATUS_UNVERIFIED = "UNVERIFIED"

IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
CIDR_RE = re.compile(r"\b((?:\d{1,3}\.){3}\d{1,3})/(\d{1,2})\b")
DOTTED_MASK_RE = re.compile(r"\b255\.(?:255|254|252|248|240|224|192|128|0)\.(?:255|254|252|248|240|224|192|128|0)\.(?:255|254|252|248|240|224|192|128|0)\b")


def _result(finding, status, evidence, explanation):
    return {
        "finding": finding,
        "status": status,
        "evidence": (evidence or "").strip(),
        "explanation": explanation,
    }


def _valid_ipv4(value):
    try:
        return ip_address(value)
    except ValueError:
        return None


def _mask_to_prefix(mask):
    try:
        return ip_network(f"0.0.0.0/{mask}").prefixlen
    except ValueError:
        return None


def _extract_ip_mask_pairs(text):
    """Extract common 'IP address X mask Y' or 'IP X/Y' pairs."""
    pairs = []
    for ip, prefix in CIDR_RE.findall(text):
        if _valid_ipv4(ip) and 0 <= int(prefix) <= 32:
            pairs.append((ip, int(prefix)))

    patterns = [
        re.compile(r"(?:ip\s+address|ipconfig|host\s+ip)\s*[:=]?\s*((?:\d{1,3}\.){3}\d{1,3})\s+((?:255\.){3}\d{1,3})", re.I),
        re.compile(r"\bIP\s*[:=]\s*((?:\d{1,3}\.){3}\d{1,3})\s+Mask\s*[:=]\s*((?:255\.){3}\d{1,3})", re.I),
    ]
    for pattern in patterns:
        for ip, mask in pattern.findall(text):
            prefix = _mask_to_prefix(mask)
            if _valid_ipv4(ip) and prefix is not None:
                pairs.append((ip, prefix))
    return pairs


def check_interface_down(evidence: str):
    text = evidence.lower()
    match = re.search(r"(?im)^\s*([a-z][\w.-]*\d(?:/\d+)?(?:/\d+)?)\s*$", evidence)
    if "administratively down" in text:
        idx = text.find("administratively down")
        window = evidence[max(0, idx - 120):idx + 40]
        return _result(
            "Interface administratively down", STATUS_ISSUE, window,
            "The interface is administratively down, which normally means it has been shut down and will not forward traffic until it is enabled with no shutdown.",
        )

    # Only treat explicit interface status/protocol columns or adjacent
    # status lines as proof. Avoid matching words like 'network down'.
    plain = re.search(
        r"(?im)^\s*([A-Za-z]+Ethernet\S*|Serial\S*|Vlan\S*)\s*$\n(?:[^\n]*\n){0,3}?\s*down\s+down\s*$",
        evidence,
    )
    if plain:
        return _result(
            f"Interface {plain.group(1)} is down/down", STATUS_ISSUE,
            plain.group(0),
            "The interface status and line protocol are both down, indicating a Layer 1/2 connectivity problem.",
        )
    return None


def check_duplicate_ip(evidence: str):
    # Count IPs in interface/address assignment lines first; avoid counting
    # repeated explanatory references as duplicate assignments.
    assignments = re.findall(
        r"(?im)^\s*(?:ip\s+address|IP(?:C|V4)?\s*(?:address)?|Host(?:\s+IP)?)\s*[:=]?\s*((?:\d{1,3}\.){3}\d{1,3})",
        evidence,
    )
    valid = [ip for ip in assignments if _valid_ipv4(ip)]
    counts = Counter(valid)
    dupes = [ip for ip, count in counts.items() if count > 1]
    if dupes:
        return _result(
            "Duplicate IP address detected", STATUS_ISSUE,
            f"IP address {dupes[0]} appears in more than one address assignment.",
            "The same IPv4 address is assigned to multiple interfaces/hosts, creating an address conflict.",
        )

    if "duplicate ip address" in evidence.lower() or "duplicate address" in evidence.lower():
        return _result(
            "Duplicate IP address reported", STATUS_ISSUE,
            "Evidence explicitly reports a duplicate IP/address condition.",
            "The supplied device output explicitly reports an address conflict.",
        )
    return None


def check_subnet_mask(evidence: str):
    pairs = _extract_ip_mask_pairs(evidence)
    if len(pairs) < 2:
        return None

    # Different masks alone are NOT a fault. Look for an explicit mismatch
    # indication, or two hosts/interfaces explicitly described as peers/same
    # subnet with incompatible networks.
    lower = evidence.lower()
    explicit = any(term in lower for term in ("mask mismatch", "wrong subnet mask", "incorrect subnet mask", "wrong mask"))
    if explicit:
        masks = sorted({prefix for _, prefix in pairs})
        return _result(
            "Subnet mask mismatch", STATUS_ISSUE,
            f"Evidence reports an incorrect/mismatched subnet mask; observed prefixes: {masks}.",
            "The evidence explicitly identifies a subnet-mask problem.",
        )

    if "same subnet" in lower or "same network" in lower:
        networks = {ip_network(f"{ip}/{prefix}", strict=False) for ip, prefix in pairs}
        if len(networks) > 1:
            return _result(
                "Subnet mask/network mismatch", STATUS_ISSUE,
                f"Addressed hosts described as being on the same network resolve to different networks: {sorted(map(str, networks))}.",
                "The supplied addresses and masks place hosts that should share a subnet into different networks.",
            )
    return None


def check_gateway_mismatch(evidence: str):
    text = evidence
    # Prefer explicit host/PC/client configuration over router interface
    # addresses. This fixes cases where both appear in the same evidence.
    host_ip = None
    host_prefix = None

    host_patterns = [
        re.compile(r"(?i)(?:PC\w*|host|client|laptop|tablet)[^\n]{0,80}?(?:IP(?: address)?)[^\d]*(\d{1,3}(?:\.\d{1,3}){3})[^\n]{0,80}?(?:Subnet|Mask)[^\d]*(255\.\d{1,3}\.\d{1,3}\.\d{1,3}|/\d{1,2})"),
        re.compile(r"(?i)IP(?: address)?\s*[:=]?\s*(\d{1,3}(?:\.\d{1,3}){3})\s*[,; ]+Subnet\s*(?:Mask)?\s*[:=]?\s*(255\.\d{1,3}\.\d{1,3}\.\d{1,3}|/\d{1,2})"),
    ]
    for p in host_patterns:
        m = p.search(text)
        if m:
            host_ip = m.group(1)
            mask = m.group(2)
            host_prefix = int(mask[1:]) if mask.startswith("/") else _mask_to_prefix(mask)
            if _valid_ipv4(host_ip) and host_prefix is not None:
                break

    gateway_match = re.search(r"(?i)(?:default\s*-?gateway|default\s+gw|gateway)\s*[:=]?\s*(\d{1,3}(?:\.\d{1,3}){3})", text)
    if not gateway_match:
        return None

    gateway = gateway_match.group(1)
    if not _valid_ipv4(gateway):
        return None

    if host_ip is None:
        # Only fall back to an explicit 'ip address ... mask' assignment.
        m = re.search(r"(?i)\bIP\s+address\s*[:=]?\s*(\d{1,3}(?:\.\d{1,3}){3})\s+(255\.\d{1,3}\.\d{1,3}\.\d{1,3})", text)
        if m:
            host_ip = m.group(1)
            host_prefix = _mask_to_prefix(m.group(2))

    if not host_ip or host_prefix is None or not _valid_ipv4(host_ip):
        return None

    try:
        network = ip_interface(f"{host_ip}/{host_prefix}").network
        gw_addr = ip_address(gateway)
    except ValueError:
        return None

    if gw_addr not in network:
        return _result(
            "Default gateway mismatch", STATUS_ISSUE,
            f"Host/client IP {host_ip}/{host_prefix} is in {network}; gateway is {gateway}.",
            "The configured default gateway is outside the host's local subnet, so the host cannot use it as its next hop.",
        )

    return _result(
        "Gateway is on the same subnet", STATUS_NONE,
        f"Host/client IP {host_ip}/{host_prefix} and gateway {gateway} are both in {network}.",
        "The supplied IP, mask, and gateway are on the same subnet.",
    )


def check_missing_vlan(evidence: str):
    text = evidence
    configured = set(re.findall(r"(?im)\bswitchport\s+(?:access\s+)?vlan\s+(\d+)\b", text))
    if not configured:
        return None

    # Parse the VLAN IDs from the show vlan brief table. Restrict parsing to
    # the table portion so interface numbers and IPs elsewhere are ignored.
    brief_match = re.search(r"(?is)show\s+vlan\s+brief(.*?)(?:\n\s*show\s+|\Z)", text)
    brief = brief_match.group(1) if brief_match else ""
    existing = set(re.findall(r"(?m)^\s*(\d{1,4})\s+\S+\s+(?:active|act/unsup|suspended|inactive)", brief, re.I))
    if not existing and brief:
        existing = set(re.findall(r"(?m)^\s*(\d{1,4})\s+\S+", brief))

    if not brief:
        return None

    missing = sorted(configured - existing, key=int)
    if missing:
        vid = missing[0]
        return _result(
            f"VLAN {vid} not created on switch", STATUS_ISSUE,
            f"Access VLAN {vid} is configured on a switchport, but show vlan brief does not list VLAN {vid}.",
            f"Ports assigned to VLAN {vid} cannot operate correctly while that VLAN is absent from the switch VLAN database.",
        )

    return _result(
        "Configured access VLANs exist", STATUS_NONE,
        f"Configured access VLANs {sorted(configured, key=int)} are present in show vlan brief.",
        "Every access VLAN explicitly configured in the supplied evidence is present in the VLAN table.",
    )


def _route_networks(route_text):
    networks = set()
    # Connected/static/dynamic route entries commonly begin with a code and
    # then contain network/prefix. Also accept a default route.
    for ip, prefix in re.findall(r"\b((?:\d{1,3}\.){3}\d{1,3})/(\d{1,2})\b", route_text):
        try:
            networks.add(ip_network(f"{ip}/{prefix}", strict=False))
        except ValueError:
            pass
    for ip, mask in re.findall(r"\b((?:\d{1,3}\.){3}\d{1,3})\s+(255\.\d{1,3}\.\d{1,3}\.\d{1,3})\b", route_text):
        prefix = _mask_to_prefix(mask)
        if prefix is not None:
            try:
                networks.add(ip_network(f"{ip}/{prefix}", strict=False))
            except ValueError:
                pass
    return networks


def check_missing_route(evidence: str):
    m = re.search(r"(?i)destination\s+network\s*[:=]?\s*((?:\d{1,3}\.){3}\d{1,3})(?:/(\d{1,2}))?", evidence)
    if not m:
        return None

    dest_ip = m.group(1)
    prefix = int(m.group(2)) if m.group(2) else 24
    try:
        destination = ip_network(f"{dest_ip}/{prefix}", strict=False)
    except ValueError:
        return _result("Invalid destination network", STATUS_UNVERIFIED, m.group(0), "The destination network could not be parsed as a valid IPv4 network.")

    route_start = re.search(r"(?i)show\s+ip\s+route", evidence)
    route_text = evidence[route_start.start():] if route_start else evidence
    # The benchmark marker "destination network:" is a requirement, not a route entry.
    route_text = re.split(r"(?i)\bdestination\s+network\s*[:=]", route_text, maxsplit=1)[0]
    routes = _route_networks(route_text)

    if destination in routes or any(destination.subnet_of(r) or r.subnet_of(destination) for r in routes):
        return _result(
            "Route to destination present", STATUS_NONE,
            f"Routing evidence contains a route covering {destination}.",
            "The supplied routing table contains a route that covers the referenced destination network.",
        )

    return _result(
        "Missing route to destination network", STATUS_ISSUE,
        f"No route covering {destination} was found in the supplied show ip route output.",
        "The routing table does not contain a route covering the referenced destination network.",
    )


_CHECKS = [
    check_interface_down,
    check_duplicate_ip,
    check_gateway_mismatch,
    check_missing_vlan,
    check_missing_route,
    check_subnet_mask,
]


def check_evidence(symptom: str, topology: str, evidence: str) -> dict:
    evidence = evidence or ""
    if len(evidence.strip()) < 8:
        return _result(
            "Insufficient evidence to verify", STATUS_UNVERIFIED, evidence,
            "The supplied evidence is too short to apply a deterministic networking rule.",
        )

    issues = []
    confirmations = []
    for check in _CHECKS:
        try:
            result = check(evidence)
        except Exception:
            result = None
        if not result:
            continue
        if result["status"] == STATUS_ISSUE:
            issues.append(result)
        elif result["status"] == STATUS_NONE:
            confirmations.append(result)

    if issues:
        return issues[0]
    if confirmations:
        return confirmations[0]

    return _result(
        "No deterministic rule matched the evidence", STATUS_UNVERIFIED, evidence,
        "The supplied evidence does not provide enough information for one of the implemented deterministic checks to verify a fault or a healthy condition.",
    )
