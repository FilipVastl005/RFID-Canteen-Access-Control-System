#define USE_ESP32

#define ENCRYPTION_PASSWORD "mysecretkey123"

const char* SSID        = "YOUR_SSID";
const char* WIFI_PASS   = "YOUR_PASSWORD";
const char* SERVER_IP   = "192.168.1.100";
const int   SERVER_PORT = 5000;
const char* API_KEY     = "mysecretkey123";

#ifdef USE_ESP32
  #include <WiFi.h>
  #include <HTTPClient.h>
  #define SS_PIN   5
  #define RST_PIN  22
#else
  #include <ESP8266WiFi.h>
  #include <ESP8266HTTPClient.h>
  #define SS_PIN   15
  #define RST_PIN   0
#endif

#include <SPI.h>
#include <MFRC522.h>
#include <Arduino.h>

MFRC522 mfrc522(SS_PIN, RST_PIN);

String buildPayload(String id, String name, int is_allowed, bool is_test) {
  String p = "{";
  p += "\"id\":\"" + id + "\",";
  p += "\"name\":\"" + name + "\",";
  p += "\"is_allowed\":" + String(is_allowed) + ",";
  p += "\"is_test\":" + String(is_test ? "true" : "false");
  p += "}";
  return p;
}

void httpPost(String path, String body) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[ERROR] WiFi not connected.");
    return;
  }
  String url = "http://" + String(SERVER_IP) + ":" + String(SERVER_PORT) + path;
#ifdef USE_ESP32
  HTTPClient http;
  http.begin(url);
#else
  WiFiClient client;
  HTTPClient http;
  http.begin(client, url);
#endif
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);
  int code = http.POST(body);
  if (code > 0) {
    Serial.println("[HTTP] " + path + " -> " + String(code) + " " + http.getString());
  } else {
    Serial.println("[HTTP] Error: " + http.errorToString(code));
  }
  http.end();
}

String extractField(String src, String key) {
  int start = src.indexOf(key + ":");
  if (start == -1) return "";
  start += key.length() + 1;
  int end = src.indexOf("_", start);
  if (end == -1) end = src.length();
  return src.substring(start, end);
}

void handleSerialCommand(String cmd) {
  cmd.trim();

  if (cmd == "add-Test") {
    httpPost("/rfid", buildPayload("TEST001", "TestUser", 1, true));
    return;
  }
  if (cmd == "log-Test") {
    httpPost("/rfid", buildPayload("TEST001", "TestUser", 1, false));
    return;
  }
  if (cmd.startsWith("add-")) {
    String body  = cmd.substring(4);
    String name  = extractField(body, "name");
    String id    = extractField(body, "isicid");
    int allowed  = extractField(body, "isallowed").toInt();
    if (name.isEmpty() || id.isEmpty()) {
      Serial.println("[CMD] Format: add-name:X_isicid:Y_isallowed:1");
      return;
    }
    httpPost("/rfid", buildPayload(id, name, allowed, true));
    return;
  }
  if (cmd.startsWith("log-")) {
    String body  = cmd.substring(4);
    String name  = extractField(body, "name");
    String id    = extractField(body, "isicid");
    int allowed  = extractField(body, "isallowed").toInt();
    if (name.isEmpty() || id.isEmpty()) {
      Serial.println("[CMD] Format: log-name:X_isicid:Y_isallowed:1");
      return;
    }
    httpPost("/rfid", buildPayload(id, name, allowed, false));
    return;
  }

  Serial.println("[CMD] Unknown: " + cmd);
}

void setup() {
  Serial.begin(115200);
  delay(100);
  SPI.begin();
  mfrc522.PCD_Init();
  Serial.println("[RFID] Ready.");
  WiFi.begin(SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println("\n[WiFi] " + WiFi.localIP().toString());
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    handleSerialCommand(cmd);
  }
  if (!mfrc522.PICC_IsNewCardPresent()) return;
  if (!mfrc522.PICC_ReadCardSerial())   return;

  String uid = "";
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    if (mfrc522.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(mfrc522.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();
  Serial.println("[RFID] " + uid);
  httpPost("/rfid", buildPayload(uid, "CARD_SCAN", 0, false));
  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();
  delay(1000);
}
