"""Exercise the real optional SDK's local PPE implementation without network access."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

pytest.importorskip("apify")


@pytest.mark.parametrize(
    "budget,rows,complete", [(0, 0, False), (1, 1, False), (2, 2, True)]
)
def test_real_sdk_respects_paid_dataset_budget_offline(
    tmp_path, budget, rows, complete
):
    root = Path(__file__).resolve().parents[1]
    script = """
import asyncio,json,sys
from apify import Actor
from microcenter_api.actor_runner import run
sys.path.insert(0,str(__import__('pathlib').Path.cwd()/'tests'))
from test_actor import Client
c=Client()
async def main():
 async with Actor:
  await Actor.set_value('INPUT',{'mode':'product','productIds':['1'],'storeIds':['195','101'],'maxProducts':1,'maxResults':2})
  result=await run(Actor,client_factory=lambda **_:c)
  data=await (await Actor.open_dataset()).get_data()
  print('RESULT:'+json.dumps({'rows':len(data.items),'calls':c.calls,'complete':result['complete'],'stop':result['stop_reason']}))
asyncio.run(main())
"""
    env = {
        k: v for k, v in os.environ.items() if not k.startswith(("APIFY_", "ACTOR_"))
    }
    env.update(
        ACTOR_TEST_PAY_PER_EVENT="1",
        ACTOR_MAX_TOTAL_CHARGE_USD=str(budget),
        APIFY_LOCAL_STORAGE_DIR=str(tmp_path),
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT:"))
    data = json.loads(line.removeprefix("RESULT:"))
    assert data["rows"] == rows and len(data["calls"]) == rows
    assert data["complete"] is complete
