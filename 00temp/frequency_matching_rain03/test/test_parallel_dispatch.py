# -*- coding: utf-8 -*-
import unittest
from unittest import mock

import runner


class _ImmediateFuture:
    def __init__(self, result):
        self._result = result

    def result(self):
        return self._result


class _FakeExecutor:
    instances = []

    def __init__(self, max_workers=None):
        self.max_workers = max_workers
        self.submitted = []
        _FakeExecutor.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def submit(self, fn, task):
        self.submitted.append(task)
        return _ImmediateFuture(fn(task))


class _FailingProcessExecutor:
    def __init__(self, *args, **kwargs):
        raise AssertionError("ProcessPoolExecutor should not manage subprocess tasks")


class ParallelDispatchTests(unittest.TestCase):
    def setUp(self):
        _FakeExecutor.instances.clear()

    def test_execute_forecast_tasks_uses_executor_for_multiple_workers(self):
        tasks = ["skip", "success", "fail"]

        def task_runner(task):
            return {"status": task, "desc": task}

        summary = runner._execute_forecast_tasks(
            tasks, max_workers=2, task_runner=task_runner, executor_cls=_FakeExecutor)

        self.assertEqual(summary, {"total": 3, "success": 1, "skip": 1, "fail": 1})
        self.assertEqual(len(_FakeExecutor.instances), 1)
        self.assertEqual(_FakeExecutor.instances[0].max_workers, 2)
        self.assertEqual(_FakeExecutor.instances[0].submitted, tasks)

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_default_lead_time_worker_count_is_eight(self):
        self.assertEqual(runner._get_lead_time_worker_count(100), 8)

    def test_execute_forecast_tasks_defaults_to_thread_executor(self):
        tasks = ["success", "skip"]

        def task_runner(task):
            return {"status": task, "desc": task}

        with mock.patch.object(runner, "ThreadPoolExecutor", _FakeExecutor):
            with mock.patch.object(runner, "ProcessPoolExecutor", _FailingProcessExecutor, create=True):
                summary = runner._execute_forecast_tasks(
                    tasks, max_workers=2, task_runner=task_runner)

        self.assertEqual(summary, {"total": 2, "success": 1, "skip": 1, "fail": 0})
        self.assertEqual(len(_FakeExecutor.instances), 1)
        self.assertEqual(_FakeExecutor.instances[0].submitted, tasks)


if __name__ == "__main__":
    unittest.main()
