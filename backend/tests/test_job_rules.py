#!/usr/bin/env python3
"""可靠任务纯规则测试（仅依赖标准库，离线可跑）。

覆盖业务诉求：
1. 重试/排队中/已出片/失败均不新增任务
2. 重跑沿用送算时快照的测点尺度
3. 旧进程迟到写入被 fencing 拦截，不能覆盖接手方出片
4. 片区编号确定性生成，重试后原编号仍可查
5. 租约超时判定与 token 递增
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.job_rules import (
    deterministic_zone_code,
    is_stale_write,
    lease_expired,
    next_fencing_token,
    should_reuse_job,
    snapshot_params,
)

PASS, FAIL = 0, 0


def check(name, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}")


print("== 1. 幂等：重试不新增任务 ==")
for status in ("queued", "running", "succeeded", "failed"):
    check(f"{status} 状态复用同一 job", should_reuse_job(status))
check("无既有任务时才允许新建", should_reuse_job(None) is False)

print("== 2. 快照：重跑沿用送算时尺度 ==")
eps, mins = snapshot_params(
    {"params": {"eps_m": 26.0, "min_samples": 3}}, 99.0, 9
)
check("读取送算快照 eps/min_samples", (eps, mins) == (26.0, 3))
eps, mins = snapshot_params({}, 26.0, 3)
check("缺快照回退系统默认口径", (eps, mins) == (26.0, 3))
eps, mins = snapshot_params(None, 26.0, 3)
check("空 input_summary 也安全回退", (eps, mins) == (26.0, 3))

print("== 3. fencing：旧进程结果不得覆盖接手方 ==")
current = {"status": "running", "worker_id": "worker-B-7", "fencing_token": 2}
check("token 过期的写入判为陈旧", is_stale_write(current, worker_id="worker-A-3", fencing_token=1))
check("同 token 但 worker 不符也拒绝", is_stale_write(current, worker_id="worker-X-9", fencing_token=2))
check("接手方本人当前 token 放行", is_stale_write(current, worker_id="worker-B-7", fencing_token=2) is False)
done = {"status": "succeeded", "worker_id": "worker-B-7", "fencing_token": 2}
check("任务已终态后任何写入拒绝", is_stale_write(done, worker_id="worker-B-7", fencing_token=2))
check("任务不存在时拒绝写入", is_stale_write(None, worker_id="worker-B-7", fencing_token=2))

print("== 4. 片区编号确定性 ==")
code1 = deterministic_zone_code("SURV-2026-1121-AM", 0)
code2 = deterministic_zone_code("SURV-2026-1121-AM", 0)
check("同批次同簇号编号稳定", code1 == code2 == "RZ-1121-AM-01")
check("不同簇号编号可区分", deterministic_zone_code("SURV-2026-1121-AM", 1) == "RZ-1121-AM-02")
check("重试后原片区编号仍可查到", code1 == "RZ-1121-AM-01")

print("== 5. 租约与 token 递增 ==")
now = datetime(2026, 11, 22, 8, 0, tzinfo=timezone.utc)
check("未持租约不算超时", lease_expired(None, now) is False)
check("租约未到期不接管", lease_expired(now + timedelta(seconds=20), now) is False)
check("租约到期可接管", lease_expired(now - timedelta(seconds=1), now))
check("每次接管 token 严格递增", next_fencing_token(1) == 2 and next_fencing_token(2) == 3)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
