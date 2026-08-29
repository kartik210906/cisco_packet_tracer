import evaluation


def test_category_scoring():
    assert evaluation._score_ai_correct("The interface is administratively down", "Interface administratively down")
    assert evaluation._score_ai_correct("A missing route is causing the problem", "Missing route to 172.16.3.0/24")
    assert evaluation._score_ai_correct("An ACL blocks the traffic", "ACL blocks inbound HTTP traffic")
    assert not evaluation._score_ai_correct("DNS is failing", "Missing route to 172.16.3.0/24")
    assert not evaluation._score_ai_correct("The network has an issue", "Missing route to 172.16.3.0/24")


if __name__ == "__main__":
    test_category_scoring()
    print("PASS: evaluation scoring tests")
