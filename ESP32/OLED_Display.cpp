#include "OLED_Display.h"
#include <Arduino.h>

// 构造函数：保存I2C引脚和地址，初始化屏幕对象
OLED_Display::OLED_Display(uint8_t sda, uint8_t scl, uint8_t addr)
    : oled(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET),
      _sda(sda), _scl(scl), _addr(addr),
      _scrollCount(0), _msgCounter(0) {
    // 清空滚动缓冲区
    for (int i = 0; i < SCROLL_LINES; i++) {
        _scrollBuffer[i] = "";
    }
}

// 初始化：启动I2C，初始化屏幕
bool OLED_Display::begin() {
    Wire.begin(_sda, _scl);
    if (!oled.begin(SSD1306_SWITCHCAPVCC, _addr)) {
        return false;
    }
    oled.setTextSize(1);
    oled.setTextColor(SSD1306_WHITE);
    clearScrollArea();      // 清滚动区，保留头部
    return true;
}

// 清空滚动区，重置序号（不清头部）
void OLED_Display::clearScrollArea() {
    _scrollCount = 0;
    _msgCounter = 0;
    for (int i = 0; i < SCROLL_LINES; i++) {
        _scrollBuffer[i] = "";
    }
    _refreshScreen();
}

// 添加一行文本，自动加序号并滚动
void OLED_Display::println(const String& text) {
    String numberedText = String(_msgCounter) + ". " + text;
    _msgCounter++;
    
    // 如果滚动区已满，整体上移一行
    if (_scrollCount >= SCROLL_LINES) {
        for (int i = 1; i < SCROLL_LINES; i++) {
            _scrollBuffer[i - 1] = _scrollBuffer[i];
        }
        _scrollBuffer[SCROLL_LINES - 1] = numberedText;
    } else {
        // 还有空位，直接追加
        _scrollBuffer[_scrollCount] = numberedText;
        _scrollCount++;
    }
    
    _refreshScreen();
}

// 刷新屏幕：固定头部 + 滚动区
void OLED_Display::_refreshScreen() {
    oled.clearDisplay();
    oled.setCursor(0, 0);
    
    // ----- 固定头部（占2行）-----
    oled.println("Serial Monitor:");
    oled.println("----------------");
    
    // ----- 滚动区（从第3行开始，共6行）-----
    oled.setCursor(0, 16);   // 每行8像素，第3行起始Y=16
    for (int i = 0; i < _scrollCount; i++) {
        oled.println(_scrollBuffer[i]);
    }
    
    oled.display();
}

// ---------- 基础操作转发 ----------
void OLED_Display::clear() {
    oled.clearDisplay();
}

void OLED_Display::display() {
    oled.display();
}

void OLED_Display::setCursor(int16_t x, int16_t y) {
    oled.setCursor(x, y);
}

void OLED_Display::print(const String& text) {
    oled.print(text);
}