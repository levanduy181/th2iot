from collector import reply_clock, CONFIG


def test_clock_reply_is_epoch_milliseconds():
    class Client:
        def publish(self, topic, payload, **kwargs):
            self.result = (topic, payload, kwargs)
    client = Client()
    reply_clock(client, b"test-clock")
    topic, payload, options = client.result
    assert topic == CONFIG["mqtt_topic"] + "/time/test-clock"
    assert len(payload) == 13 and payload.isdigit()
    assert options == {"qos": 0, "retain": False}


def test_clock_rejects_arbitrary_topics():
    class Client:
        def publish(self, *args, **kwargs):
            raise AssertionError("Invalid boot identifier must not be published")
    for payload in (b"", b"../../other", b"+", b"#", b"a" * 65, b"\xff"):
        reply_clock(Client(), payload)
