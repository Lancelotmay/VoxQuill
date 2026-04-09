# VoxQuill

**适用于 Linux 的语音输入工具，主要用于 AI 提示词与文字录入。**

**作者**: Lancelot MEI  
[English](./README.md) | [中文版](./README_zh.md)

> [!IMPORTANT]
> **开发状态与环境限制**：
>
> - 本程序当前**仅在 Ubuntu + Wayland 桌面环境**下进行了测试逻辑验证。
> - 本程序目前主要作为特定客人的**开发/个人使用工具**，缺乏跨发行版和跨显示协议（如 X11 全面适配）的深度测试。
> - 当前语音识别率略低于讯飞的手机输入法的离线模式。
> - 当前的标点添加逻辑比较简单，容易多加句号。

---

![Program Main window](./docs/Screenshot_main.png)

## (目标)核心功能

VoxQuill 提供一个浮动界面，将语音输入转换为文本并同步至其他应用程序。

- **跨平台呼出**：在 Linux 桌面环境下支持通过全局快捷键唤出编辑框。
- **语音转写与手动调整**：
  - 自动录音：内置语音激活检测 (VAD)，在唤出后自动开始录入。当前支持 `sensevoice small` 模型，支持中英日韩混合输入。
  - 文本编辑：转写结果显示在编辑框内，支持在同步前进行手动修改。
- **文本自动注入**：
  - **提交快捷键 (`Ctrl+Enter`)**：将当前编辑框内容复制到剪贴板，把焦点切回之前的活跃窗口，并尝试自动粘贴过去。
  - 在 **X11 环境** 下：自动粘贴走 `pynput` 回退路径（注：X11 环境理论上支持，但尚未正式测试）。
  - 在 **Wayland 环境** 下：程序现在会优先尝试通过 XDG Desktop Portal 的 RemoteDesktop 路径做键盘注入；只有当 Portal 不可用或授权失败时，才会回退到 `wtype` 或 `evdev/uinput`。如果全部失败，则需手动 `Ctrl+V`。
  - **录音快捷键 (`Esc`)**：仅用于开始/停止录音，不再提交文本。
- **AI 提示词辅助**：
  - 支持插入预设的提示词内容。
  - 支持前缀展开功能（识别特定缩写并替换为预设的长文本内容）。

---

## 运行程序

在确保已完成[安装指导](#安装指南)中的环境配置后，请按以下步骤运行：

1. **激活虚拟环境**：

    ```bash
    source .venv/bin/activate
    ```

2. **启动主程序**：

    ```bash
    python3 main.py
    ```

   在 Wayland 环境下，VoxQuill 现在默认优先使用原生 Wayland Qt 模式，这样焦点归还和 Portal 粘贴会处在同一套窗口模型里。
   如果要回退到旧的 XWayland 兼容模式排查问题，可以这样启动：

    ```bash
    VOXQUILL_FORCE_XCB=1 python3 main.py
    ```

3. **配置全局热键**（推荐）：
    为了实现“即按即说”，建议在系统设置中将以下命令绑定到快捷键：

    ```bash
    # 请使用**绝对路径**指向您的虚拟环境 python 解释器和 cli.py
    /path/to/VoxQuill/.venv/bin/python /path/to/VoxQuill/cli.py --command toggle
    ```

---

## 配置文件说明

程序的所有自定义行为均通过 `config/` 目录下的 JSON 文件进行管理：

- **`config/models.json`**：
  - 管理 ASR 语音模型路径及其运行参数。
  - 控制历史记录存储路径 (`history_dir`)。
  - 控制历史记录是否开启 (`history_enabled`)。
- **`config/prompts.json`**：
  - 定义 AI 提示词模板。
  - 配置快捷指令前缀（例如将 `//s` 映射为一段复杂的角色指令）。
- **`config/shortcuts.json`**：
  - 保存 UI 内快捷键绑定。
  - 快捷键处理现在统一走命名动作，后续如果增加“在 UI 里改快捷键”的设置页，可以直接复用这套动作注册机制。

---

## Ctrl+Enter 提交、回焦与历史记录

程序将 **Ctrl+Enter** 视为“提交当前文本”的核心动作。当用户在编辑框内按下它时，会触发以下联动操作：

1. **停止录音**：如果当前仍在录音，程序会先结束音频采集并冻结最终文本。
2. **剪贴板同步**：将编辑框内的最终文本复制到系统剪贴板。
3. **归还焦点**：浮动输入框主动让出焦点，让原来的目标窗口重新成为活跃窗口。
4. **本地存档 (History Logging)**：
    - 文本会被自动追加到历史记录文件中。
    - 默认存储路径为：`~/Documents/VoxQuill/History`（可在 `models.json` 中通过 `history_dir` 修改）。
    - 文件名格式：按月生成 Markdown 文件（如 `2026-03vox.md`）。
    - 内容格式：自动添加日期标题和 ISO 时间戳，保留您的每一句语音输入记录。
5. **模拟粘贴**：在支持的系统环境下，自动在光标处执行粘贴操作。
   - 在 GNOME/Wayland 下，程序会优先尝试 XDG Desktop Portal RemoteDesktop，并在可用时恢复或复用会话。
   - 如果 Portal 和回退方案都失败，程序会弹出确认提示框，同时保留剪贴板内容，方便手动 `Ctrl+V`。
6. **清空输入框**：提交非空文本后自动清空当前浮动编辑框。

**Esc** 键不再执行提交；它现在只负责切换录音状态。

---

## 技术架构

- **界面引擎**：PyQt6
- **ASR 引擎**：基于 [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) (本地离线运行)
- **静音检测**：Silero VAD v5 (ONNX 运行时)
- **进程间通信 (IPC)**：基于 JSON 的 Unix 域套接字 (Domain Sockets)
- **音频输入**：PyAudio
- **系统测试**：目前仅在 Ubuntu + Wayland 下测试。

---

## 安装指南 (Installation)

### 1. 系统依赖

需要安装 `libxcb-cursor0` 以保障在 Wayland 下的窗口定位交互逻辑。

### 2. 环境配置

```bash
git clone https://github.com/lancelotmei/VoxQuill.git
cd VoxQuill
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 下载模型

使用 **Model Manager (Ctrl+M)** 或运行脚本：

```bash
python3 scripts/download_models.py
```

---

## 已知问题

- **模拟粘贴限制 (Wayland)**：受协议安全限制，模拟粘贴功能在不同合成器（GNOME/KDE/Sway）上的表现可能不一。若无法自动粘贴，请手动完成。
- **窗口排版定位**：目前程序无法自动精准探测并跟随当前活跃的光标位置。

---

## 构建与打包

如果您需要生成独立的 Linux 可执行文件，可以运行：

```bash
./scripts/build_linux.sh
```

---

## 授权协议

**GNU GPL v3.0**
