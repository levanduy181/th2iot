#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <DHTesp.h>
#include <sys/time.h>

const char* MQTT_HOST = "host.wokwi.internal";
const uint16_t MQTT_PORT = 1884;
const char* MQTT_TOPIC = "ptit/B23DCAT074/sensors";
const int DHT_PIN = 21, TRIG_PIN = 5, ECHO_PIN = 18, LED_PIN = 23;
const uint32_t INTERVAL_MS = 5000;
WiFiClient network;
PubSubClient mqtt(network);
DHTesp dht;
char bootId[20];
char clockTopic[100];
uint32_t lastClockRequest = 0;
uint32_t sequenceNo = 0, lastSample = 0, lastConnect = 0, lastWifi = 0;

void clockReply(char* topic, byte* payload, unsigned int length) {
    if (strcmp(topic, clockTopic) != 0 || length != 13) return;
    char text[14];
    for (unsigned int i = 0; i < length; ++i) {
        if (payload[i] < '0' || payload[i] > '9') return;
        text[i] = payload[i];
    }
    text[length] = 0;
    uint64_t ms = strtoull(text, nullptr, 10);
    if (ms < 1700000000000ULL || ms > 4102444800000ULL) return;
    timeval current;
    gettimeofday(&current, nullptr);
    if (current.tv_sec >= 1700000000) return;
    timeval corrected;
    corrected.tv_sec = ms / 1000;
    corrected.tv_usec = (ms % 1000) * 1000;
    if (settimeofday(&corrected, nullptr) == 0)
        Serial.println("Clock synchronized from local MQTT collector (NTP fallback)");
}

float distanceCm() {
    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(2);
    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG_PIN, LOW);
    auto pulse = pulseIn(ECHO_PIN, HIGH, 30000);
    return pulse ? pulse * 0.0343f / 2 : NAN;
}

void jsonNumber(char* out, size_t size, float value) {
    if (isfinite(value)) snprintf(out, size, "%.2f", value);
    else snprintf(out, size, "null");
}

void setup() {
    Serial.begin(115200);
    pinMode(TRIG_PIN, OUTPUT);
    pinMode(ECHO_PIN, INPUT);
    pinMode(LED_PIN, OUTPUT);
    dht.setup(DHT_PIN, DHTesp::DHT22);
    snprintf(bootId, sizeof(bootId), "%08lx%08lx", (unsigned long)esp_random(), (unsigned long)esp_random());
    snprintf(clockTopic, sizeof(clockTopic), "%s/time/%s", MQTT_TOPIC, bootId);
    WiFi.begin("Wokwi-GUEST", "", 6);
    configTime(0, 0, "pool.ntp.org", "time.google.com");
    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqtt.setCallback(clockReply);
    mqtt.setBufferSize(768);
    mqtt.setSocketTimeout(2);
    Serial.println("\r\nBAI2 ESP32: DHT=21 TRIG=5 ECHO=18 LED=23");
    Serial.println("Waiting for WiFi and NTP...");
}

void loop() {
    uint32_t now = millis();
    if (WiFi.status() != WL_CONNECTED) {
        if (now - lastWifi > 15000) {
            lastWifi = now;
            WiFi.reconnect();
            Serial.println("WiFi reconnecting...");
        }
        delay(5);
        return;
    }
    if (!mqtt.connected() && now - lastConnect > 3000) {
        lastConnect = now;
        String clientId = String("B23DCAT074-") + bootId;
        bool connected = mqtt.connect(clientId.c_str());
        if (connected) mqtt.subscribe(clockTopic);
        Serial.printf("MQTT %s:%u %s rc=%d\r\n", MQTT_HOST, MQTT_PORT, connected ? "OK" : "FAIL", mqtt.state());
    }
    mqtt.loop();
    timeval clockNow;
    gettimeofday(&clockNow, nullptr);
    if (mqtt.connected() && clockNow.tv_sec < 1700000000 && now - lastClockRequest >= 3000) {
        lastClockRequest = now;
        String requestTopic = String(MQTT_TOPIC) + "/time/request";
        mqtt.publish(requestTopic.c_str(), bootId);
    }
    if (now - lastSample < INTERVAL_MS) { delay(2); return; }
    lastSample = now;
    ++sequenceNo;
    timeval stamp;
    gettimeofday(&stamp, nullptr);
    if (stamp.tv_sec < 1700000000) {
        Serial.println("Waiting for NTP or local MQTT clock; skip sample");
        return;
    }
    auto reading = dht.getTempAndHumidity();
    char temp[20], hum[20], dist[20];
    jsonNumber(temp, sizeof(temp), reading.temperature);
    jsonNumber(hum, sizeof(hum), reading.humidity);
    jsonNumber(dist, sizeof(dist), distanceCm());
    uint64_t epochMs = (uint64_t)stamp.tv_sec * 1000 + stamp.tv_usec / 1000;
    char payload[512];
    snprintf(payload, sizeof(payload),
        "{\"device_id\":\"B23DCAT074\",\"boot_id\":\"%s\",\"source\":\"wokwi\","
        "\"timestamp_ms\":%llu,\"sequence\":%lu,\"uptime_s\":%lu,"
        "\"temperature\":%s,\"humidity\":%s,\"distance_cm\":%s,\"rssi\":%d}",
        bootId, (unsigned long long)epochMs, (unsigned long)sequenceNo, (unsigned long)(now / 1000),
        temp, hum, dist, WiFi.RSSI());
    bool ok = mqtt.connected() && mqtt.publish(MQTT_TOPIC, payload);
    Serial.printf("%s | publish=%s\r\n", payload, ok ? "OK" : "FAILED");
    digitalWrite(LED_PIN, ok ? HIGH : LOW);
    delay(50);
    digitalWrite(LED_PIN, LOW);
}
