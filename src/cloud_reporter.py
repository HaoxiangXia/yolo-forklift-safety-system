# -*- coding: utf-8 -*-
"""
MaixCam 云端上报模块：
1. 保存报警快照
2. 通过 HTTP 上传图片并获取 image_url
3. 通过 MQTT 发布报警消息
4. 维护仅内存补传队列（不跨重启）
"""

import os
import time

import config

try:
    import ujson as json
except Exception:
    import json

try:
    import urequests as requests
except Exception:
    try:
        import requests  # type: ignore
    except Exception:
        requests = None

try:
    import paho.mqtt.client as paho_mqtt  # type: ignore
except Exception:
    paho_mqtt = None


class CloudReporter:
    """封装云端上报能力，供主循环在状态变化时调用。"""

    def __init__(self, logger=None):
        self.logger = logger
        self.device_id = getattr(config, "DEVICE_ID", "FORK-UNKNOWN")
        self.server_base_url = getattr(config, "SERVER_BASE_URL", "")
        self.upload_path = getattr(config, "UPLOAD_IMAGE_PATH", "/api/upload-image")
        self.http_timeout_s = getattr(config, "HTTP_TIMEOUT_S", 5)
        self.retry_interval_s = getattr(config, "UPLOAD_RETRY_INTERVAL_S", 5)
        self.retry_max = getattr(config, "UPLOAD_RETRY_MAX", 5)
        self.queue_maxlen = getattr(config, "UPLOAD_QUEUE_MAXLEN", 20)
        self.alarm_image_dir = getattr(config, "ALARM_IMAGE_DIR", "/root/alarm_snapshots")
        self.mqtt_topic_template = getattr(config, "MQTT_TOPIC_TEMPLATE", "factory/forklift/{device_id}/alarm")

        self._retry_queue = []
        self._mqtt_client = None
        self._mqtt_backend = None
        self._mqtt_connected = False

        if not os.path.exists(self.alarm_image_dir):
            try:
                os.makedirs(self.alarm_image_dir)
            except Exception as e:
                self._log_runtime("alarm_image_dir_create_failed", str(e))

    @staticmethod
    def make_timestamp():
        """生成 YYYY-MM-DD HH:mm:ss 格式时间戳。"""
        tm = time.localtime()
        return "%04d-%02d-%02d %02d:%02d:%02d" % (tm[0], tm[1], tm[2], tm[3], tm[4], tm[5])

    def save_snapshot(self, img, event_ts=None):
        """
        保存报警快照到本地文件，返回文件路径。
        event_ts 用于保证文件名与报警时间一致。
        """
        if img is None:
            self._log_runtime("snapshot_save_failed", "image_is_none")
            return None

        ts = event_ts if event_ts else self.make_timestamp()
        safe_ts = ts.replace(":", "-").replace(" ", "_")
        ms = int(time.time() * 1000) % 1000
        filename = "%s_%s_%03d.jpg" % (self.device_id, safe_ts, ms)
        file_path = os.path.join(self.alarm_image_dir, filename)

        try:
            quality = getattr(config, "ALARM_IMAGE_QUALITY", None)
            if quality is None:
                img.save(file_path)
            else:
                try:
                    img.save(file_path, quality=quality)
                except TypeError:
                    # 兼容不支持 quality 参数的 MaixPy 版本
                    img.save(file_path)
            return file_path
        except Exception as e:
            self._log_runtime("snapshot_save_failed", "path=%s,error=%s" % (file_path, e))
            return None

    def upload_image(self, image_path, device_id):
        """
        上传图片到服务器，成功返回 image_url，失败返回 None。
        请求格式：multipart/form-data，字段为 image + device_id。
        """
        if requests is None:
            self._log_runtime("image_upload_failed", "requests_module_missing")
            return None
        if not image_path or (not os.path.exists(image_path)):
            self._log_runtime("image_upload_failed", "invalid_image_path=%s" % image_path)
            return None

        url = self._build_upload_url()
        if not url:
            self._log_runtime("image_upload_failed", "upload_url_empty")
            return None

        response = None
        try:
            with open(image_path, "rb") as f:
                file_bytes = f.read()

            boundary = "----MaixBoundary%d" % int(time.time() * 1000)
            body = self._build_multipart_body(boundary, device_id, image_path, file_bytes)
            headers = {"Content-Type": "multipart/form-data; boundary=%s" % boundary}

            # 兼容不同 requests 实现：有的支持 timeout，有的不支持。
            try:
                response = requests.post(url, data=body, headers=headers, timeout=self.http_timeout_s)
            except TypeError:
                response = requests.post(url, data=body, headers=headers)

            status_code = getattr(response, "status_code", None)
            if status_code is None:
                status_code = getattr(response, "status", None)
            if status_code != 200:
                self._log_runtime("image_upload_failed", "status=%s,url=%s" % (status_code, url))
                return None

            payload = self._parse_response_json(response)
            image_url = payload.get("image_url")
            if not image_url:
                self._log_runtime("image_upload_failed", "response_missing_image_url")
                return None
            return image_url
        except Exception as e:
            self._log_runtime("image_upload_failed", "path=%s,error=%s" % (image_path, e))
            return None
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass

    def upload_images_batch(self, image_paths, base_timestamp):
        """
        批量上传图片到服务器，成功返回 image_urls 列表，失败返回 None。
        请求格式：multipart/form-data，字段为 device_id + base_timestamp + images(多文件)。
        """
        if requests is None:
            self._log_runtime("image_batch_upload_failed", "requests_module_missing")
            return None
        if not image_paths:
            self._log_runtime("image_batch_upload_failed", "empty_image_paths")
            return None

        valid_files = []
        for path in image_paths:
            if not path or (not os.path.exists(path)):
                self._log_runtime("image_batch_upload_failed", "invalid_image_path=%s" % path)
                continue
            try:
                with open(path, "rb") as f:
                    file_bytes = f.read()
                filename = os.path.basename(path)
                content_type = self._guess_content_type(filename)
                valid_files.append((filename, content_type, file_bytes))
            except Exception as e:
                self._log_runtime("image_batch_upload_failed", "path=%s,error=%s" % (path, e))

        if not valid_files:
            self._log_runtime("image_batch_upload_failed", "no_valid_images")
            return None

        url = self._build_upload_url()
        if not url:
            self._log_runtime("image_batch_upload_failed", "upload_url_empty")
            return None

        response = None
        try:
            boundary = "----MaixBoundary%d" % int(time.time() * 1000)
            body = self._build_multipart_body_batch(boundary, self.device_id, base_timestamp, valid_files)
            headers = {"Content-Type": "multipart/form-data; boundary=%s" % boundary}

            try:
                response = requests.post(url, data=body, headers=headers, timeout=self.http_timeout_s)
            except TypeError:
                response = requests.post(url, data=body, headers=headers)

            status_code = getattr(response, "status_code", None)
            if status_code is None:
                status_code = getattr(response, "status", None)
            if status_code != 200:
                self._log_runtime("image_batch_upload_failed", "status=%s,url=%s" % (status_code, url))
                return None

            payload = self._parse_response_json(response)
            image_urls = payload.get("image_urls")
            if not image_urls or (not isinstance(image_urls, list)):
                self._log_runtime("image_batch_upload_failed", "response_missing_image_urls")
                return None
            return image_urls
        except Exception as e:
            self._log_runtime("image_batch_upload_failed", "error=%s" % e)
            return None
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass

    def publish_alarm(self, alarm, timestamp, image_url=None, image_urls=None):
        """
        发布报警 MQTT：
        - 必带 device_id/alarm/timestamp
        - 仅在 image_urls/image_url 有值时附带图片字段
        """
        topic = self.mqtt_topic_template.format(device_id=self.device_id)
        payload = {
            "device_id": self.device_id,
            "alarm": int(alarm),
            "timestamp": timestamp,
        }
        if image_urls:
            payload["image_urls"] = image_urls
        elif image_url:
            payload["image_url"] = image_url

        payload_text = json.dumps(payload)
        return self._mqtt_publish(topic, payload_text)

    def enqueue_retry(self, image_path, event_ts):
        """
        图片上传失败后加入补传队列：
        - 队列超限时丢弃最旧项（优先保留最新报警）
        - 仅内存队列，不跨重启
        """
        if not image_path:
            return
        if len(self._retry_queue) >= self.queue_maxlen:
            dropped = self._retry_queue.pop(0)
            self._log_runtime(
                "image_retry_queue_overflow",
                "drop_oldest=%s@%s" % (dropped.get("image_path"), dropped.get("event_ts")),
            )

        self._retry_queue.append({
            "image_path": image_path,
            "event_ts": event_ts,
            "retry_count": 0,
            "next_retry_s": time.time() + self.retry_interval_s,
        })

    def tick_retry(self):
        """
        补传心跳（主循环周期调用）：
        - 每次最多处理队首 1 条，避免阻塞主循环
        - 成功后仅结束补传，不补发 MQTT，避免服务端重复记报警
        """
        if not self._retry_queue:
            return

        now_s = time.time()
        item = self._retry_queue[0]
        if now_s < item["next_retry_s"]:
            return

        image_url = self.upload_image(item["image_path"], self.device_id)
        if image_url:
            self._retry_queue.pop(0)
            self._try_delete_local_snapshot(item["image_path"])
            self._log_runtime(
                "image_retry_success",
                "path=%s,event_ts=%s,image_url=%s" % (item["image_path"], item["event_ts"], image_url),
            )
            return

        item["retry_count"] += 1
        if item["retry_count"] >= self.retry_max:
            dropped = self._retry_queue.pop(0)
            self._log_runtime(
                "image_retry_exhausted",
                "path=%s,event_ts=%s,retry_count=%d" % (
                    dropped["image_path"],
                    dropped["event_ts"],
                    dropped["retry_count"],
                ),
            )
            return

        item["next_retry_s"] = now_s + self.retry_interval_s
        self._log_runtime(
            "image_retry_scheduled",
            "path=%s,event_ts=%s,retry_count=%d" % (
                item["image_path"],
                item["event_ts"],
                item["retry_count"],
            ),
        )

    def deinit(self):
        """释放 MQTT 连接。"""
        if self._mqtt_client is None:
            return
        try:
            if self._mqtt_backend == "paho":
                self._mqtt_client.disconnect()
            self._mqtt_connected = False
        except Exception as e:
            self._log_runtime("mqtt_disconnect_failed", str(e))

    def ensure_mqtt_connected(self):
        """
        对外提供的连接检查接口：
        - 主程序可在启动阶段/定时检测时主动调用
        - 内部复用统一的连接逻辑
        """
        return self._ensure_mqtt_connected()

    def _build_upload_url(self):
        base = (self.server_base_url or "").rstrip("/")
        path = self.upload_path if self.upload_path.startswith("/") else ("/" + self.upload_path)
        return base + path if base else ""

    def _build_multipart_body(self, boundary, device_id, image_path, file_bytes):
        filename = os.path.basename(image_path)
        content_type = self._guess_content_type(filename)

        prefix = (
            "--%s\r\n"
            "Content-Disposition: form-data; name=\"device_id\"\r\n\r\n"
            "%s\r\n"
            "--%s\r\n"
            "Content-Disposition: form-data; name=\"image\"; filename=\"%s\"\r\n"
            "Content-Type: %s\r\n\r\n"
        ) % (boundary, device_id, boundary, filename, content_type)
        suffix = "\r\n--%s--\r\n" % boundary

        return prefix.encode("utf-8") + file_bytes + suffix.encode("utf-8")

    def _build_multipart_body_batch(self, boundary, device_id, base_timestamp, files):
        body = b""

        body += ("--%s\r\n" % boundary).encode("utf-8")
        body += ("Content-Disposition: form-data; name=\"device_id\"\r\n\r\n").encode("utf-8")
        body += ("%s\r\n" % device_id).encode("utf-8")

        body += ("--%s\r\n" % boundary).encode("utf-8")
        body += ("Content-Disposition: form-data; name=\"base_timestamp\"\r\n\r\n").encode("utf-8")
        body += ("%s\r\n" % base_timestamp).encode("utf-8")

        for filename, content_type, file_bytes in files:
            body += ("--%s\r\n" % boundary).encode("utf-8")
            body += (
                "Content-Disposition: form-data; name=\"images\"; filename=\"%s\"\r\n"
                % filename
            ).encode("utf-8")
            body += ("Content-Type: %s\r\n\r\n" % content_type).encode("utf-8")
            body += file_bytes
            body += b"\r\n"

        body += ("--%s--\r\n" % boundary).encode("utf-8")
        return body

    def _parse_response_json(self, response):
        try:
            if hasattr(response, "json"):
                parsed = response.json()
                if isinstance(parsed, dict):
                    return parsed
        except Exception:
            pass

        text = None
        for attr in ("text", "data", "content"):
            if hasattr(response, attr):
                text = getattr(response, attr)
                if text is not None:
                    break

        if text is None:
            return {}
        if isinstance(text, bytes):
            text = text.decode("utf-8", "ignore")
        if not isinstance(text, str):
            return {}

        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def _mqtt_publish(self, topic, payload_text):
        try:
            if not self._ensure_mqtt_connected():
                return False

            if self._mqtt_backend == "paho":
                pub_info = self._mqtt_client.publish(topic, payload_text, qos=0, retain=False)
                rc = 0
                if isinstance(pub_info, tuple):
                    rc = pub_info[0]
                else:
                    rc = getattr(pub_info, "rc", 0)
                if rc != 0:
                    self._mqtt_connected = False
                    self._log_runtime(
                        "mqtt_publish_failed",
                        "topic=%s,rc=%s,reason=%s" % (topic, rc, self._mqtt_error_string(rc))
                    )
                    return False
                return True
        except Exception as e:
            self._mqtt_connected = False
            self._log_runtime("mqtt_publish_failed", "topic=%s,error=%s" % (topic, e))
        return False

    def _guess_content_type(self, filename):
        lower_name = filename.lower()
        if lower_name.endswith(".png"):
            return "image/png"
        if lower_name.endswith(".bmp"):
            return "image/bmp"
        if lower_name.endswith(".gif"):
            return "image/gif"
        return "image/jpeg"

    def _ensure_mqtt_connected(self):
        if self._mqtt_client is None:
            if not self._init_mqtt_client():
                return False

        if self._mqtt_backend == "paho":
            # 优先使用 is_connected 判断真实 MQTT 会话状态。
            try:
                if hasattr(self._mqtt_client, "is_connected") and self._mqtt_client.is_connected():
                    self._mqtt_connected = True
                    return True
            except Exception:
                self._mqtt_connected = False

            try:
                rc = self._mqtt_client.connect(config.MQTT_BROKER, config.MQTT_PORT, 60)
                if rc != 0:
                    self._mqtt_connected = False
                    self._log_runtime(
                        "mqtt_connect_failed",
                        "broker=%s,port=%s,rc=%s,reason=%s" % (
                            config.MQTT_BROKER,
                            config.MQTT_PORT,
                            rc,
                            self._mqtt_error_string(rc),
                        ),
                    )
                    return False

                # 启动网络循环线程，保证心跳与回调正常工作。
                try:
                    self._mqtt_client.loop_start()
                except Exception as loop_e:
                    self._log_runtime("mqtt_loop_start_failed", str(loop_e))

                self._mqtt_connected = True
                print("[MQTT] 已连接 broker=%s:%s" % (config.MQTT_BROKER, config.MQTT_PORT))
                return True
            except Exception as e:
                self._log_runtime("mqtt_connect_failed", str(e))
                return False

        return False

    def _init_mqtt_client(self):
        client_id = "%s-maixcam" % self.device_id
        if paho_mqtt is not None:
            try:
                self._mqtt_client = paho_mqtt.Client(client_id=client_id)
                self._mqtt_client.on_connect = self._on_paho_connect
                self._mqtt_client.on_disconnect = self._on_paho_disconnect
                self._mqtt_backend = "paho"
                self._mqtt_connected = False
                return True
            except Exception as e:
                self._log_runtime("mqtt_init_failed", "backend=paho,error=%s" % e)

        self._log_runtime("mqtt_init_failed", "no_mqtt_backend_available")
        return False

    def _on_paho_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._mqtt_connected = True
            print("[MQTT] on_connect 成功")
        else:
            self._mqtt_connected = False
            print("[MQTT][ALARM] on_connect 失败 rc=%s reason=%s" % (rc, self._mqtt_error_string(rc)))
            self._log_runtime("mqtt_on_connect_failed", "rc=%s,reason=%s" % (rc, self._mqtt_error_string(rc)))

    def _on_paho_disconnect(self, client, userdata, rc):
        self._mqtt_connected = False
        if rc == 0:
            print("[MQTT] 已主动断开连接")
        else:
            print("[MQTT][ALARM] 非预期断开 rc=%s reason=%s" % (rc, self._mqtt_error_string(rc)))
            self._log_runtime("mqtt_unexpected_disconnect", "rc=%s,reason=%s" % (rc, self._mqtt_error_string(rc)))

    def _mqtt_error_string(self, rc):
        try:
            if paho_mqtt is not None and hasattr(paho_mqtt, "error_string"):
                return str(paho_mqtt.error_string(rc))
        except Exception:
            pass
        return "unknown"

    def _try_delete_local_snapshot(self, image_path):
        """补传成功后删除本地缓存快照，避免长期占用存储空间。"""
        if not image_path:
            return
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as e:
            self._log_runtime("snapshot_delete_failed", "path=%s,error=%s" % (image_path, e))

    def _log_runtime(self, reason, extra):
        if self.logger and hasattr(self.logger, "log_runtime_exception"):
            try:
                self.logger.log_runtime_exception(reason=reason, extra=extra)
                return
            except Exception:
                pass
        print("[CLOUD][%s] %s" % (reason, extra))
