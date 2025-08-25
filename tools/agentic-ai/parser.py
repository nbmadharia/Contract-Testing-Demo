from lxml import etree
from pathlib import Path

def parse_surefire_and_specmatic(surefire_dir: Path, specmatic_log: Path) -> str:
    sb = []
    sb.append("== Parsed Test Results ==")
    if not surefire_dir.exists():
        return f"No surefire dir: {surefire_dir}"

    for xml in sorted(surefire_dir.glob("*.xml")):
        try:
            root = etree.parse(str(xml)).getroot()
            if root.tag != "testsuite":
                continue
            name = root.attrib.get("name", xml.name)
            tests = root.attrib.get("tests", "?")
            failures = root.attrib.get("failures", "?")
            errors = root.attrib.get("errors", "?")
            sb.append(f"Suite: {name} | tests={tests} failures={failures} errors={errors}")
            for tc in root.findall("testcase"):
                tc_name = tc.attrib.get("name", "?")
                fails = tc.findall("failure")
                if fails:
                    msg = fails[0].attrib.get("message", "").strip()
                    text = (fails[0].text or "").strip()
                    sb.append(f"  FAIL: {tc_name} : {msg}")
                    if text:
                        sb.append(f"    DETAILS: {text[:2000]}")
        except Exception as e:
            sb.append(f"PARSER_ERROR: {xml.name}: {e}")

    if specmatic_log.exists():
        txt = specmatic_log.read_text(encoding="utf-8", errors="ignore")
        sb.append("\n== specmatic.log ==")
        sb.append(txt[:4000] + ("\n...truncated..." if len(txt) > 4000 else ""))
    return "\n".join(sb)
