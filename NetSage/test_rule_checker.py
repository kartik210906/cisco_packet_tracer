import rule_checker as rc


def assert_status(fn, evidence, expected):
    result = fn(evidence)
    assert result is not None, (fn.__name__, result)
    assert result["status"] == expected, (fn.__name__, result)


def test_interface_down():
    assert_status(rc.check_interface_down, "show ip interface brief\nGigabitEthernet0/0\n192.168.1.1\nadministratively down\ndown", rc.STATUS_ISSUE)
    assert_status(rc.check_interface_down, "GigabitEthernet0/0 192.168.1.1 up up", rc.STATUS_NONE) if rc.check_interface_down("GigabitEthernet0/0 192.168.1.1 up up") else True


def test_gateway_non_24():
    evidence = "PC0 config: IP 192.168.1.130, Subnet 255.255.255.128, Default Gateway 192.168.1.1"
    assert_status(rc.check_gateway_mismatch, evidence, rc.STATUS_ISSUE)
    healthy = "PC0 config: IP 192.168.1.130, Subnet 255.255.255.128, Default Gateway 192.168.1.129"
    assert_status(rc.check_gateway_mismatch, healthy, rc.STATUS_NONE)


def test_vlan_missing():
    evidence = "show vlan brief\nVLAN Name Status\n1 default active\n20 Sales active\ninterface FastEthernet0/1\n switchport access vlan 10"
    assert_status(rc.check_missing_vlan, evidence, rc.STATUS_ISSUE)


def test_route_missing_and_present():
    missing = "show ip route\nC 172.16.1.0/24 is directly connected\nC 172.16.2.0/24 is directly connected\ndestination network: 172.16.3.0/24"
    assert_status(rc.check_missing_route, missing, rc.STATUS_ISSUE)
    present = "show ip route\nC 172.16.3.0/24 is directly connected\ndestination network: 172.16.3.0/24"
    assert_status(rc.check_missing_route, present, rc.STATUS_NONE)


def test_different_masks_alone_are_not_fault():
    evidence = "IP address 10.0.0.1 255.255.255.0\nIP address 10.0.1.1 255.255.255.252"
    assert rc.check_subnet_mask(evidence) is None


def test_duplicate_ip():
    evidence = "ip address 192.168.1.10 255.255.255.0\nip address 192.168.1.10 255.255.255.0"
    assert_status(rc.check_duplicate_ip, evidence, rc.STATUS_ISSUE)


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for test in tests:
        test()
    print(f"PASS: {len(tests)} rule-checker tests")
