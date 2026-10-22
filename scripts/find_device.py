#!/usr/bin/env python3
"""在局域网中扫描 ESPectre 设备（探测 62587 端口的 /health 接口）。

用法:
    python scripts/find_device.py                # 默认扫 192.168.1.0/24
    python scripts/find_device.py --subnet 192.168.31
"""
import argparse
import concurrent.futures as futures
import http.client
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from espectre_csi.protocol import DIRECT_HTTP_PORT  # noqa: E402


def probe(ip: str):
    try:
        conn = http.client.HTTPConnection(ip, DIRECT_HTTP_PORT, timeout=0.8)
        conn.request("GET", "/espectre/v1/health",
                     headers={"Origin": "https://espectre.dev"})
        resp = conn.getresponse()
        body = resp.read(200).decode("utf-8", "replace")
        conn.close()
        if resp.status == 200:
            return ip, body
    except Exception:
        pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subnet", default="192.168.1",
                    help="网段前缀, 如 192.168.1")
    args = ap.parse_args()

    ips = [f"{args.subnet}.{i}" for i in range(1, 255)]
    print(f"扫描 {args.subnet}.0/24 的 {DIRECT_HTTP_PORT} 端口...")
    found = []
    with futures.ThreadPoolExecutor(max_workers=64) as ex:
        for r in ex.map(probe, ips):
            if r:
                found.append(r)
                print(f"  ✔ 找到 ESPectre 设备: {r[0]}")
                print(f"    {r[1][:120]}")
    if not found:
        print("  未找到设备。请确认手机/电脑与设备在同一网段，"
              "或在路由器管理页面查看设备 IP。")


if __name__ == "__main__":
    main()
