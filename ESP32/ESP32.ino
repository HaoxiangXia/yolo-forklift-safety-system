#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <time.h>
#include "OLED_Display.h"
#include "secrets.h"

#define OUT_PIN           2      // D2 输出
#define BUZZER_PIN        4      // 有源蜂鸣器（低电平触发）
#define KEY_PIN           15     // 按键

#define MAX_PACKET_LEN    64     // 最大包长度（字节）
#define PACKET_TIMEOUT_MS 100    // 包接收超时（毫秒）
#define HEARTBEAT_TIMEOUT 5000   // 心跳超时时间（毫秒）

#define MQTT_KEEPALIVE  60

WiFiClient espClient;
PubSubClient mqttClient(espClient);

unsigned long last_mqtt_publish = 0;
const unsigned long MQTT_INTERVAL = 3000; // 3秒

// 创建OLED对象，使用默认引脚21(SDA)、22(SCL)，地址0x3C
OLED_Display oled;

// 接收状态机状态定义
enum UartState {
  STATE_IDLE,      // 空闲：等待 '<'
  STATE_RECEIVING, // 接收中：等待 '>'
  STATE_DISCARD    // 丢弃模式：发生溢出后丢弃直到下一个 '<'
};

enum CommState {
  WAIT_FIRST_HB, // 开机后等待首次心跳
  COMM_OK,       // 已收到心跳，通信正常
  COMM_TIMEOUT   // 已收到过心跳，但超时未再收到
};

UartState uart_state = STATE_IDLE;
char packet_buffer[MAX_PACKET_LEN];  // 固定缓冲区，避免内存碎片
uint8_t packet_index = 0;            // 当前写入位置
unsigned long packet_start_time = 0; // 包开始接收时间

bool serial_alarm = false;
bool key_alarm = false;
CommState comm_state = WAIT_FIRST_HB;

unsigned long last_heartbeat_time = 0;

int last_key_state = HIGH;
int key_stable_state = HIGH;
unsigned long last_key_change_time = 0;

HardwareSerial MySerial(1);

void setup() {
  // 1. 初始化两个串口
  Serial.begin(115200);
  MySerial.begin(115200, SERIAL_8N1, 16, 17); // RX=16, TX=17

  // 2. GPIO初始化
  pinMode(OUT_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(KEY_PIN, INPUT_PULLUP);

  // 3. 初始状态
  digitalWrite(OUT_PIN, LOW);      // D2输出关闭
  digitalWrite(BUZZER_PIN, HIGH);  // 蜂鸣器不响（低电平触发）

  // 4. 通信状态初始化
  last_heartbeat_time = 0;
  comm_state = WAIT_FIRST_HB;

  // 5. 按键状态初始化（消抖相关）
  last_key_state = digitalRead(KEY_PIN);
  key_stable_state = last_key_state;
  last_key_change_time = millis();

  // 6. 连接网络、MQTT、同步时间
  connectWiFi();
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  initTime();

  // 7. 初始化OLED
  if (!oled.begin()) {
      Serial.println("OLED初始化失败！");
      while (1);   // 严重错误，死循环
  }
  oled.println("System Ready!");
}

/**
 * @brief 简单的校验和计算（和值取模 256）
 * 格式：<DATA,CHECKSUM>
 */
uint8_t calculateChecksum(const char* data, uint8_t len) {
  uint8_t sum = 0;
  for (uint8_t i = 0; i < len; i++) {
    sum += (uint8_t)data[i];   // 累加每个字节的ASCII值
  }
  return sum;
}

/**
 * @brief 解析完整的包内容（完全使用 C 风格字符串，避免内存碎片）
 * @param packet 缓冲区指针（格式如 "<ALARM:1>" 或 "<ALARM:1,4A>"）
 * @param len 数据长度
 */
void parsePacket(char* packet, uint8_t len) {
  if (len < 3) return; 

  char* dataStart = packet + 1; 
  // 分离数据和校验和（如果有逗号）
  char* commaPos = strchr(dataStart, ',');

  if (commaPos != NULL) {
    // 含有校验和，将其截断以便处理数据部分
    *commaPos = '\0';
    char* checksumStr = commaPos + 1;
    uint8_t receivedSum = (uint8_t)strtol(checksumStr, NULL, 16);
    uint8_t calculatedSum = calculateChecksum(dataStart, strlen(dataStart));
    
    if (receivedSum != calculatedSum) {
      Serial.println("[UART_ERROR] Checksum mismatch!");
      oled.println("[UART_ERROR] Checksum mismatch!");
      return;
    }
    // 校验通过，dataStart 现在指向的是纯数据部分
  } else {
    // 不含校验和，去掉末尾的 '>'
    if (len > 0 && packet[len-1] == '>') {
      packet[len-1] = '\0';
    }
  }

  // 使用 strcmp 进行指令比对，完全避免 String 动态分配
  if (strcmp(dataStart, "ALARM:1") == 0) {
    serial_alarm = true;
    Serial.println("[UART] Alarm ON");
  }
  else if (strcmp(dataStart, "ALARM:0") == 0) {
    serial_alarm = false;
    Serial.println("[UART] Alarm OFF");
  }
  else if (strcmp(dataStart, "HB") == 0) {
    comm_state = COMM_OK;
    last_heartbeat_time = millis();
    Serial.println("[UART] Heartbeat");
    oled.println("[UART] Heartbeat");
  }
  else {
    Serial.print("[UART] Unknown packet data: ");
    Serial.println(dataStart);
  }
}

/**
 * @brief 串口接收处理函数（包含超时和溢出保护）
 */
void handleSerialReceive() {
  // 1. 超时检测：如果处于接收状态且超过预设时间未完成，则重置
  if (uart_state == STATE_RECEIVING && (millis() - packet_start_time > PACKET_TIMEOUT_MS)) {
    Serial.println("[UART_ERROR] Receive timeout, dropping buffer");
    uart_state = STATE_IDLE;
    packet_index = 0;
  }

  // 2. 循环读取可用数据
  while (MySerial.available()) {
    char c = MySerial.read();

    if (uart_state == STATE_DISCARD) {
      if (c == '<') {
        uart_state = STATE_RECEIVING;
        packet_index = 0;
        packet_start_time = millis();
        packet_buffer[packet_index++] = c;
      }
      continue;
    }

    if (c == '<') {
      // 发现起始符，开始接收
      uart_state = STATE_RECEIVING;
      packet_index = 0;
      packet_start_time = millis();
      packet_buffer[packet_index++] = c;
    }
    else if (uart_state == STATE_RECEIVING) {
      // 3. 溢出检查：防止 packet_index 越界（留一个位置给结束符或 null）
      if (packet_index >= MAX_PACKET_LEN - 1) {
        Serial.println("[UART_ERROR] Buffer overflow, packet too long");
        uart_state = STATE_DISCARD;
        packet_index = 0;
        continue;
      }

      packet_buffer[packet_index++] = c;

      if (c == '>') {
        // 4. 发现结束符，进行解析
        packet_buffer[packet_index] = '\0'; // 结尾补零方便处理
        parsePacket(packet_buffer, packet_index);
        uart_state = STATE_IDLE;
        packet_index = 0;
      }
    }
  }
}

//WiFi 连接函数
void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting WiFi");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi Connected");
}

//MQTT 连接函数
void connectMQTT() {
  if (mqttClient.connected()) return;

  while (!mqttClient.connected()) {
    Serial.print("Connecting MQTT...");
    if (WiFi.status() != WL_CONNECTED) {
      connectWiFi();  // 先连WiFi
      return;         // 下次loop再试MQTT
    }
    if (mqttClient.connect(DEVICE_ID)) {
      Serial.println("Connected");
    } else {
      Serial.print("Failed, rc=");
      Serial.println(mqttClient.state());
      delay(2000);
    }
  }
}

//时间初始化（用于生成 timestamp）
void initTime() {
  configTime(8 * 3600, 0, "pool.ntp.org");  // 东八区
}

// 获取时间字符串
String getTimestamp() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    return "1970-01-01 00:00:00";
  }

  char buffer[20];
  strftime(buffer, sizeof(buffer), "%Y-%m-%d %H:%M:%S", &timeinfo);
  return String(buffer);
}

// MQTT 发布函数
void publishAlarm(int alarm_state) {
  String topic = "factory/forklift/";
  topic += DEVICE_ID;
  topic += "/alarm";

  String payload = "{";
  payload += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
  payload += "\"alarm\":" + String(alarm_state) + ",";
  payload += "\"timestamp\":\"" + getTimestamp() + "\"";
  payload += "}";

  mqttClient.publish(topic.c_str(), payload.c_str());
}

void loop() {
  unsigned long now = millis();

  /* ---------- 串口接收处理 ---------- */
  handleSerialReceive();

  /* ---------- 心跳超时检测 ---------- */
  // 仅在 COMM_OK 状态下检查超时
  if (comm_state == COMM_OK && (now - last_heartbeat_time > HEARTBEAT_TIMEOUT)) {
    comm_state = COMM_TIMEOUT;
  }

  /* ---------- 按键触发（20ms 防抖） ---------- */
  int current_key_state = digitalRead(KEY_PIN);
  if (current_key_state != last_key_state) {
    last_key_change_time = now;
    last_key_state = current_key_state;
  }

  if ((now - last_key_change_time) > 20 && key_stable_state != last_key_state) {
    key_stable_state = last_key_state;
  }

  key_alarm = (key_stable_state == LOW);

  /* ---------- 报警逻辑 ---------- */
  // WAIT_FIRST_HB  → 不报警
  // COMM_OK        → 正常逻辑
  // COMM_TIMEOUT   → 强制报警（通信故障）
  bool comm_fault = (comm_state == COMM_TIMEOUT);
  bool alarm_active = serial_alarm || key_alarm || comm_fault;

  if (alarm_active) {
    digitalWrite(OUT_PIN, HIGH);      // D2 高电平
    digitalWrite(BUZZER_PIN, LOW);    // 蜂鸣器响
  } else {
    digitalWrite(OUT_PIN, LOW);
    digitalWrite(BUZZER_PIN, HIGH);   // 蜂鸣器停
  }

  connectWiFi();
  connectMQTT();
  mqttClient.loop();

  if (millis() - last_mqtt_publish > MQTT_INTERVAL) {
    last_mqtt_publish = millis();

    int alarm_state = alarm_active ? 1 : 0;
    publishAlarm(alarm_state);
  }
}
