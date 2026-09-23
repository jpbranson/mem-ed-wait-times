import hashlib
import io
import json

from botocore.exceptions import ClientError


def error(code):
    return ClientError({"Error": {"Code": code}}, "S3")


class MemoryS3:
    def __init__(self):
        self.objects = {}
        self.reads = []
        self.fail_put = None
        self.conflict_once = False

    def put_object(self, Bucket, Key, Body, **kwargs):
        if self.fail_put and self.fail_put in Key:
            raise error("AccessDenied")
        current = self.objects.get((Bucket, Key))
        if self.conflict_once and Key == "data/latest.json":
            self.conflict_once = False
            raise error("PreconditionFailed")
        if kwargs.get("IfNoneMatch") == "*" and current:
            raise error("PreconditionFailed")
        if "IfMatch" in kwargs and (not current or current["ETag"] != kwargs["IfMatch"]):
            raise error("PreconditionFailed")
        value = {**kwargs, "Body": Body, "ETag": '"' + hashlib.sha256(Body).hexdigest() + '"', "Size": len(Body)}
        self.objects[Bucket, Key] = value
        return {"ETag": value["ETag"]}

    def head_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise error("NoSuchKey")
        return self.objects[Bucket, Key]

    def get_object(self, Bucket, Key, **kwargs):
        self.reads.append(Key)
        value = self.head_object(Bucket, Key)
        if "IfMatch" in kwargs and value["ETag"] != kwargs["IfMatch"]:
            raise error("PreconditionFailed")
        return {**value, "Body": io.BytesIO(value["Body"])}

    def get_paginator(self, name):
        return self

    def paginate(self, Bucket, Prefix):
        objects = [{"Key": key, "ETag": value["ETag"], "Size": value["Size"]}
                   for (bucket, key), value in self.objects.items() if bucket == Bucket and key.startswith(Prefix)]
        # Exercise pagination, including an empty page.
        yield {}
        for obj in reversed(objects):
            yield {"Contents": [obj]}

    def json(self, bucket, key):
        return json.loads(self.objects[bucket, key]["Body"])


def record(facility="memphis", wait=30, batch="2026-09-13T23:59:00+00:00", observed="2026-09-14T00:00:05+00:00", metric="CV_ED_Wait"):
    return dict(facility=facility, wait_minutes=wait, batch_id=batch, observed_at=observed, metric=metric, latency_ms=100)


def attempt(batch="2026-09-13T23:59:00+00:00", state="success"):
    return {"batch_id": batch, "attempted_at": batch, "state": state,
            "error_code": None if state == "success" else "request_failed"}
