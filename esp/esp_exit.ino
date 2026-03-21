#define USE_ESP32

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

void postUnlog(String cardId) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[ERROR] WiFi not connected.");
    return;
  }
  String url  = "http://" + String(SERVER_IP) + ":" + String(SERVER_PORT) + "/unlog";
  String body = "{\"id\":\"" + cardId + "\"}";
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
    String resp = http.getString();
    Serial.println("[UNLOG] " + String(code) + " " + resp);
    if (resp.indexOf("UNLOGGED") >= 0)   Serial.println("[OK] Checked out: " + cardId);
    if (resp.indexOf("NOT_INSIDE") >= 0) Serial.println("[WARN] Not inside: " + cardId);
  } else {
    Serial.println("[UNLOG] Error: " + http.errorToString(code));
  }
  http.end();
}

void handleSerialCommand(String cmd) {
  cmd.trim();
  if (cmd == "status") {
    Serial.println(WiFi.status() == WL_CONNECTED ? "[OK] Connected: " + WiFi.localIP().toString() : "[ERR] Disconnected");
    return;
  }
  if (cmd == "unlog-Test") {
    postUnlog("TEST001");
    return;
  }
  if (cmd.startsWith("unlog-")) {
    String cardId = cmd.substring(6);
    cardId.trim();
    if (cardId.isEmpty()) {
      Serial.println("[CMD] Usage: unlog-<cardId>");
      return;
    }
    postUnlog(cardId);
    return;
  }
  Serial.println("[CMD] Unknown. Valid: unlog-<id> | unlog-Test | status");
}

void setup() {
  Serial.begin(115200);
  delay(100);
  SPI.begin();
  mfrc522.PCD_Init();
  Serial.println("[RFID] Exit reader ready.");
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
  Serial.println("[RFID] Exit scan: " + uid);
  postUnlog(uid);
  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();
  delay(1000);
}
