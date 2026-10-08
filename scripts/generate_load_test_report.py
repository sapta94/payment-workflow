"""Generate a self-contained HTML report for one saved load-test scenario."""

# The report is intentionally self-contained: its embedded HTML/CSS/JavaScript
# uses browser-oriented line lengths rather than Python's usual line length.
# ruff: noqa: E501, I001

import argparse
import asyncio
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


REPORT_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Load Test Report</title>
<style>body{margin:0;background:#0b1220;color:#edf2f8;font:15px/1.4 system-ui,sans-serif}main{max-width:1180px;margin:auto;padding:32px 20px}h1{margin:0}p{color:#aebccc}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:24px 0}.card,.chart{background:#121d2d;border:1px solid #28384d;border-radius:12px;padding:16px}.label{color:#aebccc;font-size:12px}.value{font-size:25px;font-weight:700;margin-top:5px}.chart{margin:16px 0}canvas{display:block;width:100%;height:310px}table{width:100%;border-collapse:collapse}th,td{border-bottom:1px solid #28384d;padding:10px;text-align:right}th:first-child,td:first-child{text-align:left}@media(max-width:700px){.cards{grid-template-columns:repeat(2,1fr)}}</style>
</head><body><main><h1>Payment API Load Test</h1><p id="scenario"></p><section class="cards" id="cards"></section><section class="chart"><h2>Latency by requested load</h2><canvas id="latency" width="1120" height="310"></canvas></section><section class="chart"><h2>Achieved traffic by second</h2><canvas id="traffic" width="1120" height="310"></canvas></section><section class="chart"><h2>Phase results</h2><table><thead><tr><th>Target RPS</th><th>Achieved RPS</th><th>Requests</th><th>HTTP errors</th><th>Average</th><th>P50</th><th>P95</th><th>P99</th></tr></thead><tbody id="rows"></tbody></table></section>
<script>const runs=__RUNS__;const colors=['#75a7ff','#25c281','#ffc857','#ed83e5','#ff906e'];
const number=n=>Number(n).toFixed(2);document.querySelector('#scenario').textContent=`Scenario ${runs[0].scenario_id} · ${runs[0].target_url}`;
const allRequests=runs.reduce((sum,run)=>sum+run.completed_requests,0),allErrors=runs.reduce((sum,run)=>sum+run.http_error_count,0);document.querySelector('#cards').innerHTML=[['Phases',runs.length],['Requests',allRequests],['HTTP errors',allErrors],['Max p95',`${number(Math.max(...runs.map(r=>r.p95_latency_ms)))} ms`]].map(([label,value])=>`<article class="card"><div class="label">${label}</div><div class="value">${value}</div></article>`).join('');
document.querySelector('#rows').innerHTML=runs.map(r=>`<tr><td>${r.requested_rps}</td><td>${number(r.achieved_rps)}</td><td>${r.completed_requests}</td><td>${r.http_error_count}</td><td>${number(r.average_latency_ms)} ms</td><td>${number(r.p50_latency_ms)} ms</td><td>${number(r.p95_latency_ms)} ms</td><td>${number(r.p99_latency_ms)} ms</td></tr>`).join('');
function bars(canvasId,labels,series,unit){const c=document.querySelector(canvasId),x=c.getContext('2d'),w=c.width,h=c.height,p={l:48,r:20,t:22,b:42},max=Math.max(1,...series.flatMap(s=>s.values));x.clearRect(0,0,w,h);x.font='11px system-ui';for(let i=0;i<=4;i++){const v=max*i/4,y=h-p.b-(h-p.t-p.b)*i/4;x.strokeStyle='#28384d';x.beginPath();x.moveTo(p.l,y);x.lineTo(w-p.r,y);x.stroke();x.fillStyle='#aebccc';x.fillText(`${number(v)}${unit}`,4,y+4)}const group=(w-p.l-p.r)/labels.length,bar=group/(series.length+1);labels.forEach((label,i)=>{series.forEach((s,j)=>{const value=s.values[i],bh=(h-p.t-p.b)*value/max,bx=p.l+i*group+(j+.5)*bar,by=h-p.b-bh;x.fillStyle=s.color;x.fillRect(bx,by,bar-3,bh)});x.fillStyle='#aebccc';x.fillText(label,p.l+i*group+4,h-16)})}
bars('#latency',runs.map(r=>`${r.requested_rps} RPS`),[{name:'P95',color:colors[0],values:runs.map(r=>r.p95_latency_ms)},{name:'P99',color:colors[2],values:runs.map(r=>r.p99_latency_ms)}],' ms');
const trafficRuns=runs.map((r,i)=>({name:`${r.requested_rps} RPS`,color:colors[i%colors.length],values:r.per_second_metrics.map(m=>m.completed_requests)})),maxSeconds=Math.max(...trafficRuns.map(s=>s.values.length));bars('#traffic',Array.from({length:maxSeconds},(_,i)=>`s${i+1}`),trafficRuns,'');
</script></main></body></html>"""


async def load_runs(database_url: str, scenario_id: str) -> list[dict]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(
                text(
                    "SELECT * FROM test_runs "
                    "WHERE scenario_id = :scenario_id ORDER BY requested_rps",
                ),
                {"scenario_id": scenario_id},
            )
            results = [dict(row) for row in rows.mappings()]
    finally:
        await engine.dispose()

    for result in results:
        metrics = result["per_second_metrics"]
        result["per_second_metrics"] = json.loads(metrics) if isinstance(metrics, str) else metrics
        for key, value in tuple(result.items()):
            if isinstance(value, Decimal):
                result[key] = float(value)
            elif hasattr(value, "isoformat"):
                result[key] = value.isoformat()
    return results


async def async_main(arguments: argparse.Namespace) -> int:
    database_url = os.getenv("LOAD_TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("Set LOAD_TEST_DATABASE_URL or DATABASE_URL before generating a report")
    runs = await load_runs(database_url, arguments.scenario_id)
    if not runs:
        raise ValueError(f"No test_runs rows found for scenario {arguments.scenario_id}")

    output_path = Path(arguments.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(REPORT_TEMPLATE.replace("__RUNS__", json.dumps(runs)), encoding="utf-8")
    print(f"Report written to {output_path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an HTML load-test report")
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--output", default="reports/load-test-report.html")
    arguments = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(async_main(arguments)))
    except ValueError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
