from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from book_to_skill.config import OUTPUT_DIR

# CEB（方正 Apabi 电子书）是专有二进制格式，方正未公开规范，Python 生态
# 没有可靠的开源解析库。这里采用三级降级策略：
#   1) 外部转换工具（用户通过 BOOK_SKILL_CEB_CONVERTER 配置命令）
#   2) ZIP 包裹的 CEB（部分 CEB 实为 zip，内含 XML/文本）
#   3) 二进制里的可读字符串提取（最后手段，尽力而为）

# 外部转换工具的命令模板，{input} / {output} 会被替换。
# 例：export BOOK_SKILL_CEB_CONVERTER="ceb2txt {input} {output}"
_CEB_CONVERTER_TEMPLATE = os.environ.get("BOOK_SKILL_CEB_CONVERTER", "")

# 常见 CEB 转换工具名（按优先级探测）
_CEB_TOOL_CANDIDATES = ("ceb2txt", "ceb2pdf", "cebtool", "apabi")


def extract_ceb(input_path: str) -> str | None:
    text = _try_external_converter(input_path)
    if text:
        return text
    text = _try_zip_extract(input_path)
    if text:
        return text
    return _try_string_extract(input_path)


def _try_external_converter(input_path: str) -> str | None:
    """调用用户配置的转换工具，输出为 TXT。"""
    template = _CEB_CONVERTER_TEMPLATE.strip()
    cmd = None
    output_is_file = False

    if template:
        if "{input}" in template and "{output}" in template:
            out_path = OUTPUT_DIR / "ceb-convert-output.txt"
            cmd = template.replace("{input}", input_path).replace("{output}", str(out_path))
            cmd = [p for p in cmd.split(" ") if p]
            output_is_file = True
        else:
            # 假定模板是单命令（读 stdout）
            cmd = [p for p in template.replace("{input}", input_path).split(" ") if p]
            output_is_file = False
    else:
        # 探测常见工具名，约定 "tool input output.txt"
        for name in _CEB_TOOL_CANDIDATES:
            if shutil.which(name):
                out_path = OUTPUT_DIR / "ceb-convert-output.txt"
                cmd = [name, input_path, str(out_path)]
                output_is_file = True
                break

    if not cmd:
        return None

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if output_is_file:
            out_path = OUTPUT_DIR / "ceb-convert-output.txt"
            if result.returncode == 0 and out_path.exists():
                text = out_path.read_text(encoding="utf-8", errors="replace")
                if text.strip():
                    return text
        else:
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
    except Exception as e:
        print(
            f"  [warn] CEB external converter failed: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
    return None


def _try_zip_extract(input_path: str) -> str | None:
    """部分 CEB 文件其实是 zip 容器，尝试解包提取 XML/文本。"""
    try:
        with zipfile.ZipFile(input_path) as zf:
            names = zf.namelist()
            text_parts = []
            for name in names:
                if name.lower().endswith((".xml", ".txt", ".html", ".htm", ".opf", ".ncx")):
                    try:
                        raw = zf.read(name)
                        text_parts.append(_decode_lenient(raw))
                    except Exception:
                        continue
            if text_parts:
                joined = "\n\n".join(p for p in text_parts if p and p.strip())
                if joined.strip():
                    return joined
    except (zipfile.BadZipFile, OSError):
        pass
    return None


def _try_string_extract(input_path: str) -> str | None:
    """最后手段：从二进制里抓取连续可读文本段（中文/英文/数字/标点）。"""
    try:
        raw = Path(input_path).read_bytes()
    except OSError:
        return None

    def _runs(decoded: str) -> str:
        runs = re.findall(
            r"[\u4e00-\u9fffA-Za-z0-9，。！？；：、（）《》“”‘’\-\.,;:!?()\"' ]{8,}",
            decoded,
        )
        meaningful = [r.strip() for r in runs if len(r.strip()) >= 8]
        # 去重（相邻重复的 run 是压缩/索引噪声）
        deduped = []
        prev = ""
        for r in meaningful:
            if r != prev:
                deduped.append(r)
            prev = r
        return "\n".join(deduped)

    # 优先 UTF-8：现代文件主流编码。GBK 字节大多不是合法 UTF-8，会被
    # errors="ignore" 丢弃，因此 UTF-8 结果「够多」就说明原文就是 UTF-8；
    # 否则再用 gb18030 兜底（中文电子书常见 GBK 编码）。
    try:
        utf8_text = _runs(raw.decode("utf-8", errors="ignore"))
    except (UnicodeDecodeError, LookupError):
        utf8_text = ""
    if len(utf8_text) >= 8:
        return utf8_text

    try:
        gb_text = _runs(raw.decode("gb18030", errors="ignore"))
    except (UnicodeDecodeError, LookupError):
        gb_text = ""
    return gb_text if gb_text.strip() else (utf8_text if utf8_text.strip() else None)


def _decode_lenient(raw: bytes) -> str | None:
    for enc in ("utf-8", "gb18030", "gbk", "big5", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return None
