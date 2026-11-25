"""The public ngrok share (the owner: "Public, as ruled"): the edge adds
noindex and no referrer; no credential sits in the policy or in the repo."""

from chole_demo import share


def test_the_policy_blocks_indexing_and_carries_no_credential():
    pol = share.policy()
    assert "on_http_request" not in pol  # viewing is public; asking is gated by the demo server
    headers = pol["on_http_response"][0]["actions"][0]["config"]["headers"]
    assert headers == {"x-robots-tag": "noindex, nofollow", "referrer-policy": "no-referrer"}


def test_the_policy_file_lives_outside_git():
    assert share.POLICY.parts[-3:] == ("runs", "share", "policy.yml")
    ignored = (share.REPO / ".gitignore").read_text().splitlines()
    assert "runs/" in ignored and "configs/*.local.yaml" in ignored
