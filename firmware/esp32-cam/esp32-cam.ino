#include "esp_camera.h"
#include <WiFi.h>
#include <esp_http_server.h>

// =============== WIFI CONFIGURATION ===============
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// =============== AI THINKER ESP32-CAM PINS ===============
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// =============== SETTINGS ===============
const unsigned long WIFI_RETRY_INTERVAL = 10000;

unsigned long lastWiFiRetry = 0;

bool cameraReady = false;
bool cameraServersStarted = false;

httpd_handle_t streamServer = nullptr;
httpd_handle_t controlServer = nullptr;

// =============== CAMERA INITIALIZATION ===============
bool initCamera() {

  camera_config_t config = {};

  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;

  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;

  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;

  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;

  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;

  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = 12;
  config.fb_count = 2;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_LATEST;

  esp_err_t error = esp_camera_init(&config);

  if (error != ESP_OK) {
    Serial.printf("Camera initialization failed: 0x%x\n", error);
    return false;
  }

  Serial.println("Camera initialized successfully");
  return true;
}

// =============== CORS HEADERS ===============
void addCorsHeaders(httpd_req_t* request) {

  httpd_resp_set_hdr(
    request,
    "Access-Control-Allow-Origin",
    "*"
  );

  httpd_resp_set_hdr(
    request,
    "Cache-Control",
    "no-store, no-cache, must-revalidate"
  );

  httpd_resp_set_hdr(
    request,
    "Pragma",
    "no-cache"
  );
}

// =============== LIVE STREAM HANDLER ===============
static const char* STREAM_CONTENT_TYPE =
  "multipart/x-mixed-replace;boundary=frame";

static const char* STREAM_BOUNDARY =
  "\r\n--frame\r\n";

static const char* STREAM_PART =
  "Content-Type: image/jpeg\r\n"
  "Content-Length: %u\r\n\r\n";

static esp_err_t streamHandler(httpd_req_t* request) {

  esp_err_t result = httpd_resp_set_type(
    request,
    STREAM_CONTENT_TYPE
  );

  if (result != ESP_OK) {
    return result;
  }

  addCorsHeaders(request);

  Serial.println("ESP32-CAM live stream client connected");

  char partHeader[64];

  while (true) {

    camera_fb_t* frame = esp_camera_fb_get();

    if (!frame) {
      Serial.println("Stream frame capture failed");
      result = ESP_FAIL;
      break;
    }

    size_t headerLength = snprintf(
      partHeader,
      sizeof(partHeader),
      STREAM_PART,
      (unsigned int)frame->len
    );

    result = httpd_resp_send_chunk(
      request,
      STREAM_BOUNDARY,
      strlen(STREAM_BOUNDARY)
    );

    if (result == ESP_OK) {
      result = httpd_resp_send_chunk(
        request,
        partHeader,
        headerLength
      );
    }

    if (result == ESP_OK) {
      result = httpd_resp_send_chunk(
        request,
        (const char*)frame->buf,
        frame->len
      );
    }

    esp_camera_fb_return(frame);

    if (result != ESP_OK) {
      break;
    }

    vTaskDelay(pdMS_TO_TICKS(40));
  }

  Serial.println("ESP32-CAM stream client disconnected");

  return result;
}

// =============== SINGLE PHOTO CAPTURE ===============
static esp_err_t captureHandler(httpd_req_t* request) {

  addCorsHeaders(request);

  camera_fb_t* frame = esp_camera_fb_get();

  if (!frame) {
    Serial.println("Photo capture failed");
    httpd_resp_send_500(request);
    return ESP_FAIL;
  }

  httpd_resp_set_type(
    request,
    "image/jpeg"
  );

  httpd_resp_set_hdr(
    request,
    "Content-Disposition",
    "inline; filename=crop.jpg"
  );

  esp_err_t result = httpd_resp_send(
    request,
    (const char*)frame->buf,
    frame->len
  );

  Serial.printf(
    "Photo captured: %u bytes\n",
    (unsigned int)frame->len
  );

  esp_camera_fb_return(frame);

  return result;
}

// =============== CAMERA STATUS ===============
static esp_err_t statusHandler(httpd_req_t* request) {

  addCorsHeaders(request);

  httpd_resp_set_type(
    request,
    "application/json"
  );

  const char* response =
    "{\"camera\":\"online\",\"board\":\"AI Thinker ESP32-CAM\"}";

  return httpd_resp_send(
    request,
    response,
    HTTPD_RESP_USE_STRLEN
  );
}

// =============== START CAMERA SERVERS ===============
void startCameraServers() {

  if (cameraServersStarted) {
    return;
  }

  httpd_config_t streamConfig = HTTPD_DEFAULT_CONFIG();
  streamConfig.server_port = 81;
  streamConfig.ctrl_port = 32769;
  streamConfig.max_uri_handlers = 2;
  streamConfig.stack_size = 8192;

  if (httpd_start(&streamServer, &streamConfig) != ESP_OK) {
    streamServer = nullptr;
    Serial.println("ESP32-CAM stream server failed to start");
    return;
  }

  httpd_uri_t streamUri = {};
  streamUri.uri = "/stream";
  streamUri.method = HTTP_GET;
  streamUri.handler = streamHandler;
  streamUri.user_ctx = nullptr;

  esp_err_t result = httpd_register_uri_handler(streamServer, &streamUri);
  if (result != ESP_OK) {
    Serial.printf("Failed to register /stream: %s\n", esp_err_to_name(result));
    httpd_stop(streamServer);
    streamServer = nullptr;
    return;
  }

  httpd_config_t controlConfig = HTTPD_DEFAULT_CONFIG();
  controlConfig.server_port = 80;
  controlConfig.ctrl_port = 32768;
  controlConfig.max_uri_handlers = 4;

  if (httpd_start(&controlServer, &controlConfig) != ESP_OK) {
    controlServer = nullptr;
    httpd_stop(streamServer);
    streamServer = nullptr;
    Serial.println("ESP32-CAM control server failed to start");
    return;
  }

  httpd_uri_t captureUri = {};
  captureUri.uri = "/capture";
  captureUri.method = HTTP_GET;
  captureUri.handler = captureHandler;
  captureUri.user_ctx = nullptr;

  result = httpd_register_uri_handler(controlServer, &captureUri);
  if (result != ESP_OK) {
    Serial.printf("Failed to register /capture: %s\n", esp_err_to_name(result));
    httpd_stop(controlServer);
    controlServer = nullptr;
    httpd_stop(streamServer);
    streamServer = nullptr;
    return;
  }

  httpd_uri_t statusUri = {};
  statusUri.uri = "/status";
  statusUri.method = HTTP_GET;
  statusUri.handler = statusHandler;
  statusUri.user_ctx = nullptr;

  result = httpd_register_uri_handler(controlServer, &statusUri);
  if (result != ESP_OK) {
    Serial.printf("Failed to register /status: %s\n", esp_err_to_name(result));
    httpd_stop(controlServer);
    controlServer = nullptr;
    httpd_stop(streamServer);
    streamServer = nullptr;
    return;
  }

  cameraServersStarted = true;

  Serial.println("\nESP32-CAM servers started");
  Serial.print("LIVE STREAM: http://");
  Serial.print(WiFi.localIP());
  Serial.println(":81/stream");
  Serial.print("CAPTURE PHOTO: http://");
  Serial.print(WiFi.localIP());
  Serial.println(":80/capture");
  Serial.print("CAMERA STATUS: http://");
  Serial.print(WiFi.localIP());
  Serial.println(":80/status");
}

// =============== WIFI CONNECTION ===============
bool connectWiFi() {

  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }

  Serial.println("\nConnecting to Wi-Fi...");

  WiFi.begin(
    WIFI_SSID,
    WIFI_PASSWORD
  );

  unsigned long startTime = millis();

  while (
    WiFi.status() != WL_CONNECTED &&
    millis() - startTime < 15000
  ) {
    delay(300);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWi-Fi connected");
    Serial.print("ESP32-CAM IP: ");
    Serial.println(WiFi.localIP());
    return true;
  }

  Serial.println("\nWi-Fi connection failed");
  return false;
}

// =============== SETUP ===============
void setup() {

  Serial.begin(115200);
  delay(1000);

  Serial.println("\n");
  Serial.println("================================");
  Serial.println("DRONE CROP DISEASE AI");
  Serial.println("AI THINKER ESP32-CAM");
  Serial.println("================================");

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);

  cameraReady = initCamera();

  if (!cameraReady) {
    Serial.println("Camera unavailable. Check camera ribbon and power.");
    return;
  }

  if (connectWiFi()) {
    startCameraServers();
  } else {
    Serial.println("Waiting for Wi-Fi connection...");
  }
}

// =============== MAIN LOOP ===============
void loop() {

  if (!cameraReady) {
    delay(1000);
    return;
  }

  unsigned long currentTime = millis();

  if (
    WiFi.status() != WL_CONNECTED &&
    currentTime - lastWiFiRetry >= WIFI_RETRY_INTERVAL
  ) {
    lastWiFiRetry = currentTime;
    Serial.println("Wi-Fi disconnected. Reconnecting...");

    if (connectWiFi()) {
      startCameraServers();
    }
  }

  delay(20);
}
