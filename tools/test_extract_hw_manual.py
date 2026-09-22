# -*- coding: utf-8 -*-
from extract_hw_manual import decode_html_bytes, find_volumes, html_to_text, parse_hhc


HHC = """<!DOCTYPE HTML PUBLIC>
<HTML><BODY><OBJECT type="text/site">
<param name="Name" value="手册">
<param name="Local" value="index.htm">
</OBJECT><UL>
<LI><OBJECT><param name="Name" value="配置指南">
<param name="Local" value="config.htm"></OBJECT>
<UL>
<LI><OBJECT><param name="Name" value="VLAN配置">
<param name="Local" value="vlan.htm"></OBJECT></LI>
</UL></LI>
<LI><OBJECT><param name="Name" value="告警处理">
<param name="Local" value="alarm_root.htm"></OBJECT></LI>
</UL></BODY></HTML>
"""


def test_parse_hhc_nested_paths():
    items = parse_hhc(HHC)
    assert [(i["name"], i["local"]) for i in items] == [
        ("手册", "index.htm"),
        ("配置指南", "config.htm"),
        ("VLAN配置", "vlan.htm"),
        ("告警处理", "alarm_root.htm"),
    ]
    assert items[2]["path"] == "手册/配置指南/VLAN配置"


HTML = """<html><head><meta charset="utf-8"><script>evil()</script>
<style>.x{}</style></head><body>
<h1>命令功能</h1>
<table><tr><td>vlan-id</td><td>VLAN编号(整数)</td></tr>
<tr><td>name</td><td>VLAN名称</td></tr></table>
<p>取值 a &lt; b &amp;&amp; b &gt; c</p><br><p>第二行</p>
</body></html>
"""


def test_html_to_text_strips_script_keeps_table():
    out = html_to_text(HTML)
    assert "evil()" not in out and ".x{}" not in out
    assert "命令功能" in out
    assert "vlan-id | VLAN编号(整数)" in out
    assert "取值 a < b && b > c" in out


def test_find_volumes_by_top_segments():
    items = parse_hhc(HHC) + [
        {"name": "OSPF", "local": "o.htm", "path": "手册/命令参考/OSPF"},
        {"name": "日志A", "local": "l.htm", "path": "手册/日志参考/日志A"},
        {"name": "安装", "local": "i.htm", "path": "手册/安装指南/安装"},
    ]
    vols = find_volumes(items)
    assert [i["local"] for i in vols["配置指南"]] == ["config.htm", "vlan.htm"]
    assert [i["local"] for i in vols["告警处理"]] == ["alarm_root.htm"]
    assert [i["local"] for i in vols["命令参考"]] == ["o.htm"]
    assert [i["local"] for i in vols["日志参考"]] == ["l.htm"]
    assert all("安装" not in v["path"] for vol in vols.values() for v in vol)


def test_find_volumes_accepts_cli_variant_name():
    items = [{"name": "命令行参考", "local": "c.htm", "path": "手册/命令行参考"}]
    assert [i["local"] for i in find_volumes(items)["命令参考"]] == ["c.htm"]


def test_decode_html_bytes_utf8_and_gbk():
    utf8 = '<html><meta charset="utf-8"><body>环回口</body></html>'.encode("utf-8")
    assert "环回口" in decode_html_bytes(utf8)
    gbk = '<html><body>聚合口</body></html>'.encode("gbk")
    assert "聚合口" in decode_html_bytes(gbk)
    declared = '<html><meta charset="gbk"><body>千兆口</body></html>'.encode("gbk")
    assert "千兆口" in decode_html_bytes(declared)
