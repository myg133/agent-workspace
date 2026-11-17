# vendored MQTT library

本目录是 **paho-mqtt 2.2.0** 的源码副本，用于避免运行时 `pip install`。

- upstream: https://github.com/eclipse-paho/paho.mqtt.python
- version: 2.2.0
- wheel: `paho_mqtt-2.2.0-py3-none-any.whl`
- wheel sha256: `3243630f7c2b05f71d1de8c6f59865eb04d3a59ae8c866e92377faed6753db4d`
- license: EPL-2.0 / EDL-1.0（见 `LICENSES/paho-mqtt/`）
- local changes: none

## 使用

不要把 `vendor` 当普通包安装。把 `vendor` 加入 `sys.path` 即可：

```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "vendor"))
import paho.mqtt.client as mqtt
```

这样导入的是仓库内的 paho，不会命中用户环境里已安装的版本。

## 升级

1. 下载新版本 wheel；
2. 替换 `vendor/paho/`；
3. 替换 `vendor/LICENSES/paho-mqtt/`；
4. 更新 `VERSION` 与本文的 sha256；
5. 跑 `tests/test_aw_single.py` 里的 import 测试。

不要直接修改 `vendor/paho` 源码；需要 patch 时单独记录在 `vendor/patches/`。

## 为什么 vendor

- 不希望每个 agent 机器都执行 `pip install`；
- paho 是纯 Python，无 C 扩展，适合直接随仓库分发；
- MQTT 只在 watcher 中使用，客户端插件仍然只读本地文件。
