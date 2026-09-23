# Mock cloud SDKs for the cloud days: installs in-memory fakes of `boto3` / `botocore` (S3, SQS,
# Secrets Manager, Bedrock Runtime converse) and of `google.cloud` (storage, bigquery, secretmanager,
# pubsub_v1), `google.api_core.exceptions` and `google.genai` (Gemini on Vertex AI).
#
# Call shapes, response shapes, errors and the SDKs' own habits follow the real libraries for
# the parts the course uses (checked against the official docs and the SDK sources), e.g.:
# boto3 methods take keyword arguments only, validate parameter names, sign (and so need
# credentials) on the first call, and retry throttling / 5xx errors by themselves (legacy mode:
# 5 attempts); google-cloud clients retry idempotent calls; BigQuery reports query errors from
# job.result(). Anything the mock does not implement raises NotImplementedError, so a learner
# never gets a silently wrong answer.
#
# Loaded as the module `_cccloud` (its names never mix with the learner's); install with
#   import _cccloud; CLOUD = _cccloud._cc_cloud_install(dataset_sql)
# The BigQuery client runs SQL on SQLite with the BigQuery helpers of py_sql.py (`_ccsql`).
import base64 as _b64
import datetime as _dt
import hashlib as _hashlib
import io as _io
import itertools as _itertools
import enum as _enum
import json as _json
import math as _math
import random as _random
import re as _re
import sqlite3 as _sqlite3
import sys as _sys
import types as _types
import urllib.parse as _urlparse
import uuid as _uuid

NOW = _dt.datetime(2026, 9, 23, 12, 0, 0, tzinfo=_dt.timezone.utc)
PROJECT = "clausecheck-dev"
PROJECT_NUMBER = "123456789012"
ACCOUNT = "123456789012"
REGION = "eu-north-1"
_STATE = {"cloud": None}



def _tr(zh, en):
    """The page's language: __main__._CC_LANG is "en" when the page is in English."""
    import __main__
    return en if getattr(__main__, "_CC_LANG", "zh") == "en" else zh


def _module(name, **attrs):
    mod = _types.ModuleType(name)
    mod.__dict__.update(attrs)
    _sys.modules[name] = mod
    return mod


def _cloud():
    return _STATE["cloud"]


# ======================================================================== AWS: botocore
class BotoCoreError(Exception):
    fmt = "An unspecified error occurred"

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        super().__init__(self.fmt.format(**kwargs))


class NoCredentialsError(BotoCoreError):
    fmt = "Unable to locate credentials"


class NoRegionError(BotoCoreError):
    fmt = "You must specify a region."


class ParamValidationError(BotoCoreError):
    fmt = "Parameter validation failed:\n{report}"


class InvalidRetryConfigurationError(BotoCoreError):
    fmt = 'Cannot provide retry configuration for "{retry_config_option}". Valid retry configuration options are: {valid_options}'


class InvalidRetryModeError(InvalidRetryConfigurationError):
    fmt = 'Invalid value provided to "mode": "{provided_retry_mode}" must be one of: {valid_modes}'


class InvalidMaxRetryAttemptsError(InvalidRetryConfigurationError):
    fmt = 'Value provided to "max_attempts": {provided_max_attempts} must be an integer greater than or equal to {min_value}.'


class ClientError(Exception):
    """botocore.exceptions.ClientError: e.response["Error"]["Code"] tells what went wrong."""

    def __init__(self, error_response, operation_name):
        self.response = error_response
        self.operation_name = operation_name
        err = error_response.get("Error", {})
        meta = error_response.get("ResponseMetadata", {})
        retry = f" (reached max retries: {meta.get('RetryAttempts')})" if meta.get("MaxAttemptsReached") else ""
        super().__init__(f"An error occurred ({err.get('Code', 'Unknown')}) when calling the {operation_name} operation{retry}: {err.get('Message', 'Unknown')}")


class Config:
    """botocore.config.Config (only region_name and retries are used by the mock)."""

    def __init__(self, region_name=None, retries=None, **kwargs):
        # like botocore: a bad retries dict fails here, when the Config is created
        for key, value in (retries or {}).items():
            if key not in ("max_attempts", "mode", "total_max_attempts"):
                raise InvalidRetryConfigurationError(retry_config_option=key, valid_options=("max_attempts", "mode", "total_max_attempts"))
            if key == "mode" and value not in ("legacy", "standard", "adaptive"):
                raise InvalidRetryModeError(provided_retry_mode=value, valid_modes=("legacy", "standard", "adaptive"))
            if key == "max_attempts" and (not isinstance(value, int) or value < 0):
                raise InvalidMaxRetryAttemptsError(provided_max_attempts=value, min_value=0)
            if key == "total_max_attempts" and (not isinstance(value, int) or value < 1):
                raise InvalidMaxRetryAttemptsError(provided_max_attempts=value, min_value=1)
        self.region_name, self.retries = region_name, dict(retries or {})
        self.other = kwargs


def _meta(cloud, status=200, retries=0):
    return {"RequestId": cloud.request_id(), "HTTPStatusCode": status, "HTTPHeaders": {}, "RetryAttempts": retries}


# what botocore retries by itself (legacy and standard modes)
_RETRYABLE_CODES = {"Throttling", "ThrottlingException", "ThrottledException", "RequestThrottledException",
                    "TooManyRequestsException", "ProvisionedThroughputExceededException", "RequestLimitExceeded",
                    "BandwidthLimitExceeded", "LimitExceededException", "RequestThrottled", "SlowDown",
                    "ServiceUnavailable", "ServiceUnavailableException", "InternalError", "InternalServerException"}


class _Op:
    def __init__(self, name, required, implemented, params, types=None, ignored=()):
        self.name, self.required, self.implemented = name, required, set(implemented) | set(ignored)
        self.params, self.types = params, types or {}


def _type_name(t):
    return {bytes: "<class 'bytes'>", bytearray: "<class 'bytearray'>", str: "<class 'str'>", int: "<class 'int'>",
            dict: "<class 'dict'>", list: "<class 'list'>", tuple: "<class 'tuple'>", float: "<class 'float'>",
            bool: "<class 'bool'>", "file": "file-like object", _dt.datetime: "<class 'datetime.datetime'>",
            "blob": "<class 'bytes'>, <class 'bytearray'>, file-like object"}[t]


def _is_type(v, types):
    for t in types:
        if t == "blob":  # botocore blobs: bytes, bytearray, str or a file-like object
            if isinstance(v, (bytes, bytearray, str)) or hasattr(v, "read"):
                return True
        elif t == "file":
            if hasattr(v, "read"):
                return True
        elif t is int:
            if isinstance(v, int) and not isinstance(v, bool):
                return True
        elif t is float:
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return True
        elif isinstance(v, t):
            return True
    return False


class _AwsClient:
    _SERVICE = ""
    _OPS = {}
    _EXCEPTIONS = ()
    _CODE_TO_EXC = {}

    def __init__(self, cloud, region, config):
        self._c = cloud
        retries = (config.retries if config else {}) or {}
        mode = retries.get("mode", "legacy")
        if retries.get("total_max_attempts") is not None:
            self._attempts = int(retries["total_max_attempts"])
        elif retries.get("max_attempts") is not None:
            self._attempts = int(retries["max_attempts"]) + 1
        else:
            self._attempts = 5 if mode == "legacy" else 3
        self.meta = _types.SimpleNamespace(region_name=region, service_model=_types.SimpleNamespace(service_name=self._SERVICE))
        exc = {"ClientError": ClientError}
        for name in self._EXCEPTIONS:
            exc[name] = type(name, (ClientError,), {"__module__": "botocore.errorfactory"})
        self.exceptions = _types.SimpleNamespace(**exc)

    def __repr__(self):
        return f"<botocore.client.{type(self).__name__} object (mock)>"

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        op = type(self)._OPS.get(name)
        if op is None:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

        def api_call(*args, **kwargs):
            if args:
                raise TypeError(f"{name}() only accepts keyword arguments.")
            self._validate(op, kwargs)
            self._c.sign()
            retries = self._c.maybe_fail(self._SERVICE, self, op.name, self._attempts)
            out = getattr(self, "_" + name)(**kwargs)
            out.setdefault("ResponseMetadata", _meta(self._c, 200, retries))
            out["ResponseMetadata"]["RetryAttempts"] = retries
            return out
        api_call.__name__ = name
        return api_call

    def can_paginate(self, operation_name):
        return operation_name in getattr(self, "_PAGINATORS", {})

    def _validate(self, op, kwargs):
        report = []
        for k in op.required:
            if k not in kwargs:
                report.append(f'Missing required parameter in input: "{k}"')
        for k, v in kwargs.items():
            if k not in op.params:
                report.append(f'Unknown parameter in input: "{k}", must be one of: {", ".join(op.params)}')
            elif k in op.types and not _is_type(v, op.types[k]):
                report.append(f"Invalid type for parameter {k}, value: {v}, type: {type(v)}, valid types: {', '.join(_type_name(t) for t in op.types[k])}")
        report += self._validate_nested(op.name, kwargs)
        if report:
            raise ParamValidationError(report="\n".join(report))
        for mv in (kwargs.get("Metadata") or {}).values() if isinstance(kwargs.get("Metadata"), dict) else ():
            if not isinstance(mv, str):  # what botocore 1.43 raises when it serialises the x-amz-meta-* headers
                raise AttributeError(f"'{type(mv).__name__}' object has no attribute 'encode'")
        missing = sorted(k for k in kwargs if k not in op.implemented)
        if missing:
            raise NotImplementedError(_tr(f"本页的模拟没有实现 {op.name} 的参数 {', '.join(missing)}（真 SDK 支持）", f"this page's simulation does not implement the {op.name} parameter(s) {', '.join(missing)} (the real SDK does)"))

    def _validate_nested(self, op_name, kwargs):
        return []

    def _error(self, code, message, op, status=400, extra=None, retries=0, max_reached=False):
        meta = _meta(self._c, status, retries)
        if max_reached:
            meta["MaxAttemptsReached"] = True
        err = {"Code": code, "Message": message, **(extra or {})}
        cls = getattr(self.exceptions, self._CODE_TO_EXC.get(code, code), None)
        cls = cls if isinstance(cls, type) and issubclass(cls, ClientError) else ClientError
        return cls({"Error": err, "ResponseMetadata": meta}, op)


class _Body:
    """botocore.response.StreamingBody over bytes."""

    def __init__(self, data):
        self._raw = _io.BytesIO(data)
        self._len = len(data)

    def read(self, amt=None):
        return self._raw.read() if amt is None else self._raw.read(amt)

    def iter_chunks(self, chunk_size=1024):
        while True:
            chunk = self.read(chunk_size)
            if not chunk:
                return
            yield chunk

    def iter_lines(self, chunk_size=1024, keepends=False):
        for line in self._raw.read().splitlines(keepends):
            yield line

    def readlines(self):
        return self._raw.read().splitlines(True)

    def __iter__(self):
        return self.iter_chunks()

    def close(self):
        self._raw.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def __repr__(self):
        return "<botocore.response.StreamingBody object (mock)>"


def _as_bytes(body):
    if body is None:
        return b""
    if isinstance(body, (bytes, bytearray)):
        return bytes(body)
    if isinstance(body, str):
        return body.encode("utf-8")
    data = body.read()
    return data.encode("utf-8") if isinstance(data, str) else bytes(data)


_S3_GET_PARAMS = ["Bucket", "IfMatch", "IfModifiedSince", "IfNoneMatch", "IfUnmodifiedSince", "Key", "Range",
                  "ResponseCacheControl", "ResponseContentDisposition", "ResponseContentEncoding", "ResponseContentLanguage",
                  "ResponseContentType", "ResponseExpires", "VersionId", "SSECustomerAlgorithm", "SSECustomerKey",
                  "SSECustomerKeyMD5", "RequestPayer", "PartNumber", "ExpectedBucketOwner", "ChecksumMode"]


class S3(_AwsClient):
    _SERVICE = "s3"
    _EXCEPTIONS = ("NoSuchKey", "NoSuchBucket", "NoSuchUpload", "BucketAlreadyExists", "BucketAlreadyOwnedByYou",
                   "InvalidObjectState", "ObjectAlreadyInActiveTierError", "ObjectNotInActiveTierError")
    _PAGINATORS = {"list_objects_v2"}
    _OPS = {
        "create_bucket": _Op("CreateBucket", ["Bucket"], ["Bucket", "CreateBucketConfiguration"],
                             ["ACL", "Bucket", "CreateBucketConfiguration", "GrantFullControl", "GrantRead", "GrantReadACP",
                              "GrantWrite", "GrantWriteACP", "ObjectLockEnabledForBucket", "ObjectOwnership"],
                             {"Bucket": [str], "CreateBucketConfiguration": [dict]}),
        "put_object": _Op("PutObject", ["Bucket", "Key"], ["Bucket", "Key", "Body", "ContentType", "Metadata", "IfNoneMatch"],
                          ["ACL", "Body", "Bucket", "CacheControl", "ContentDisposition", "ContentEncoding", "ContentLanguage",
                           "ContentLength", "ContentMD5", "ContentType", "ChecksumAlgorithm", "ChecksumCRC32", "ChecksumCRC32C",
                           "ChecksumCRC64NVME", "ChecksumSHA1", "ChecksumSHA256", "Expires", "IfMatch", "IfNoneMatch",
                           "GrantFullControl", "GrantRead", "GrantReadACP", "GrantWriteACP", "Key", "WriteOffsetBytes",
                           "Metadata", "ServerSideEncryption", "StorageClass", "WebsiteRedirectLocation", "SSECustomerAlgorithm",
                           "SSECustomerKey", "SSECustomerKeyMD5", "SSEKMSKeyId", "SSEKMSEncryptionContext", "BucketKeyEnabled",
                           "RequestPayer", "Tagging", "ObjectLockMode", "ObjectLockRetainUntilDate", "ObjectLockLegalHoldStatus",
                           "ExpectedBucketOwner"],
                          {"Bucket": [str], "Key": [str], "Body": ["blob"], "ContentType": [str], "Metadata": [dict],
                           "IfNoneMatch": [str]},
                          ignored=["CacheControl", "ContentDisposition", "ContentEncoding", "ContentLanguage", "StorageClass",
                                   "ServerSideEncryption", "ExpectedBucketOwner"]),
        "get_object": _Op("GetObject", ["Bucket", "Key"], ["Bucket", "Key"], _S3_GET_PARAMS,
                          {"Bucket": [str], "Key": [str]}, ignored=["ExpectedBucketOwner"]),
        "head_object": _Op("HeadObject", ["Bucket", "Key"], ["Bucket", "Key"], _S3_GET_PARAMS,
                           {"Bucket": [str], "Key": [str]}, ignored=["ExpectedBucketOwner"]),
        "delete_object": _Op("DeleteObject", ["Bucket", "Key"], ["Bucket", "Key"],
                             ["Bucket", "Key", "MFA", "VersionId", "RequestPayer", "BypassGovernanceRetention",
                              "ExpectedBucketOwner", "IfMatch", "IfMatchLastModifiedTime", "IfMatchSize"],
                             {"Bucket": [str], "Key": [str]}, ignored=["ExpectedBucketOwner"]),
        "list_objects_v2": _Op("ListObjectsV2", ["Bucket"], ["Bucket", "Prefix", "MaxKeys", "ContinuationToken", "StartAfter", "Delimiter"],
                               ["Bucket", "Delimiter", "EncodingType", "MaxKeys", "Prefix", "ContinuationToken", "FetchOwner",
                                "StartAfter", "RequestPayer", "ExpectedBucketOwner", "OptionalObjectAttributes"],
                               {"Bucket": [str], "Prefix": [str], "MaxKeys": [int], "ContinuationToken": [str], "StartAfter": [str],
                                "Delimiter": [str]}, ignored=["ExpectedBucketOwner"]),
    }

    def _bucket(self, name, op, head=False):
        if name not in self._c.s3:
            if head:  # HEAD responses have no body: the code is just the status
                raise self._error("404", "Not Found", op, 404)
            raise self._error("NoSuchBucket", "The specified bucket does not exist", op, 404, {"BucketName": name})
        return self._c.s3[name]

    def _create_bucket(self, Bucket, CreateBucketConfiguration=None):
        region = self.meta.region_name
        lc = (CreateBucketConfiguration or {}).get("LocationConstraint")
        if region != "us-east-1" and lc != region:
            msg = ("The unspecified location constraint is incompatible for the region specific endpoint this request was sent to."
                   if lc is None else f"The {lc} location constraint is incompatible for the region specific endpoint this request was sent to.")
            raise self._error("IllegalLocationConstraintException", msg, "CreateBucket")
        if Bucket in self._c.s3:
            raise self._error("BucketAlreadyOwnedByYou", "Your previous request to create the named bucket succeeded and you already own it.", "CreateBucket", 409, {"BucketName": Bucket})
        self._c.s3[Bucket] = {}
        self._c.calls.append(("s3.create_bucket", Bucket))
        return {"Location": f"/{Bucket}" if region == "us-east-1" else f"http://{Bucket}.s3.amazonaws.com/"}

    def _put_object(self, Bucket, Key, Body=b"", ContentType="binary/octet-stream", Metadata=None, IfNoneMatch=None, **ignored):
        objects = self._bucket(Bucket, "PutObject")
        if IfNoneMatch is not None:
            if IfNoneMatch != "*":
                raise NotImplementedError(_tr("本页的模拟只支持 IfNoneMatch='*'（对象不存在时才写入）", "this page's simulation only supports IfNoneMatch='*' (write only if the object does not exist)"))
            if Key in objects:
                raise self._error("PreconditionFailed", "At least one of the pre-conditions you specified did not hold", "PutObject", 412, {"Condition": "If-None-Match"})
        data = _as_bytes(Body)
        etag = '"' + _hashlib.md5(data).hexdigest() + '"'
        objects[Key] = {"Body": data, "ContentType": ContentType, "Metadata": {k.lower(): v for k, v in (Metadata or {}).items()},
                        "ETag": etag, "LastModified": self._c.clock()}
        self._c.calls.append(("s3.put_object", Bucket, Key))
        return {"ETag": etag}

    def _get_object(self, Bucket, Key, **ignored):
        objects = self._bucket(Bucket, "GetObject")
        self._c.calls.append(("s3.get_object", Bucket, Key))
        if Key not in objects:
            raise self._error("NoSuchKey", "The specified key does not exist.", "GetObject", 404, {"Key": Key})
        o = objects[Key]
        return {"Body": _Body(o["Body"]), "ContentLength": len(o["Body"]), "ContentType": o["ContentType"], "ETag": o["ETag"],
                "LastModified": o["LastModified"], "Metadata": dict(o["Metadata"]), "AcceptRanges": "bytes"}

    def _head_object(self, Bucket, Key, **ignored):
        objects = self._bucket(Bucket, "HeadObject", head=True)
        if Key not in objects:
            raise self._error("404", "Not Found", "HeadObject", 404)
        o = objects[Key]
        return {"ContentLength": len(o["Body"]), "ContentType": o["ContentType"], "ETag": o["ETag"],
                "LastModified": o["LastModified"], "Metadata": dict(o["Metadata"]), "AcceptRanges": "bytes"}

    def _delete_object(self, Bucket, Key, **ignored):
        self._bucket(Bucket, "DeleteObject").pop(Key, None)  # deleting a missing key is not an error in S3
        self._c.calls.append(("s3.delete_object", Bucket, Key))
        out = {}
        out["ResponseMetadata"] = _meta(self._c, 204)
        return out

    def _list_objects_v2(self, Bucket, Prefix="", MaxKeys=1000, ContinuationToken=None, StartAfter=None, Delimiter=None, **ignored):
        objects = self._bucket(Bucket, "ListObjectsV2")
        self._c.calls.append(("s3.list_objects_v2", Bucket, Prefix))
        entries = []  # (sort key, kind, value)
        seen_prefixes = set()
        for k in sorted(objects):
            if not k.startswith(Prefix or ""):
                continue
            if Delimiter:
                cut = k.find(Delimiter, len(Prefix or ""))
                if cut >= 0:
                    p = k[:cut + len(Delimiter)]
                    if p not in seen_prefixes:
                        seen_prefixes.add(p)
                        entries.append((p, "prefix", p))
                    continue
            entries.append((k, "key", k))
        entries.sort()
        after = StartAfter
        if ContinuationToken is not None:
            after = self._c.s3_tokens.get(ContinuationToken)
            if after is None:
                raise self._error("InvalidArgument", "The continuation token provided is incorrect", "ListObjectsV2", 400,
                                  {"ArgumentName": "continuation-token"})
        if after:
            entries = [e for e in entries if e[0] > after]
        size = min(MaxKeys, 1000)
        page, rest = entries[:size], entries[size:]
        out = {"IsTruncated": bool(rest), "Name": Bucket, "Prefix": Prefix or "", "MaxKeys": MaxKeys, "KeyCount": len(page)}
        keys = [e[2] for e in page if e[1] == "key"]
        if keys:  # like the real API, "Contents" is missing when nothing matched
            out["Contents"] = [{"Key": k, "LastModified": objects[k]["LastModified"], "ETag": objects[k]["ETag"],
                                "Size": len(objects[k]["Body"]), "StorageClass": "STANDARD"} for k in keys]
        prefixes = [e[2] for e in page if e[1] == "prefix"]
        if Delimiter:
            out["Delimiter"] = Delimiter
        if prefixes:
            out["CommonPrefixes"] = [{"Prefix": p} for p in prefixes]
        if ContinuationToken is not None:
            out["ContinuationToken"] = ContinuationToken
        if StartAfter is not None:
            out["StartAfter"] = StartAfter
        if rest:
            token = _b64.b64encode(("1" + _uuid.UUID(int=self._c.rng.getrandbits(128)).hex).encode()).decode()
            self._c.s3_tokens[token] = page[-1][0]
            out["NextContinuationToken"] = token
        return out

    def get_paginator(self, operation_name):
        if operation_name != "list_objects_v2":
            raise NotImplementedError(_tr(f"本页的模拟只有 list_objects_v2 的分页器，没有 {operation_name}", f"this page's simulation only has a paginator for list_objects_v2, not for {operation_name}"))
        client = self

        class _Paginator:
            def paginate(self, **kwargs):
                cfg = dict(kwargs.pop("PaginationConfig", None) or {})
                if cfg.get("PageSize"):
                    kwargs["MaxKeys"] = cfg["PageSize"]
                limit = cfg.get("MaxItems")

                def pages():
                    token, count = cfg.get("StartingToken"), 0
                    while True:
                        args = dict(kwargs)
                        if token:
                            args["ContinuationToken"] = token
                        page = client.list_objects_v2(**args)
                        if limit is not None and "Contents" in page:
                            page["Contents"] = page["Contents"][: max(0, limit - count)]
                            count += len(page["Contents"])
                        yield page
                        token = page.get("NextContinuationToken")
                        if not token or (limit is not None and count >= limit):
                            return
                return pages()

        return _Paginator()

    def generate_presigned_url(self, ClientMethod, Params=None, ExpiresIn=3600, HttpMethod=None):
        if ClientMethod not in ("get_object", "put_object"):
            raise NotImplementedError(_tr("本页的模拟只能为 get_object / put_object 生成预签名 URL", "this page's simulation can only presign get_object / put_object"))
        if not 1 <= ExpiresIn <= 604800:
            raise ParamValidationError(report=f"Invalid value for parameter ExpiresIn, value: {ExpiresIn}, valid range: 1-604800")
        self._c.sign()  # presigning signs locally, so it also needs credentials
        p = Params or {}
        key = _urlparse.quote(p.get("Key", ""), safe="/")
        return (f"https://{p.get('Bucket')}.s3.{self.meta.region_name}.amazonaws.com/{key}?X-Amz-Algorithm=AWS4-HMAC-SHA256"
                f"&X-Amz-Credential=MOCKACCESSKEY%2F20260923%2F{self.meta.region_name}%2Fs3%2Faws4_request&X-Amz-Date=20260923T120000Z"
                f"&X-Amz-Expires={ExpiresIn}&X-Amz-SignedHeaders=host&X-Amz-Signature=mock")


class SQS(_AwsClient):
    """At-least-once delivery with a visibility timeout on a fake clock (CLOUD.advance(seconds))."""
    _SERVICE = "sqs"
    _EXCEPTIONS = ("QueueDoesNotExist", "ReceiptHandleIsInvalid", "InvalidMessageContents", "OverLimit", "InvalidAttributeName")
    _CODE_TO_EXC = {"AWS.SimpleQueueService.NonExistentQueue": "QueueDoesNotExist"}
    _OPS = {
        "create_queue": _Op("CreateQueue", ["QueueName"], ["QueueName", "Attributes"], ["QueueName", "Attributes", "tags"],
                            {"QueueName": [str], "Attributes": [dict]}),
        "get_queue_url": _Op("GetQueueUrl", ["QueueName"], ["QueueName"], ["QueueName", "QueueOwnerAWSAccountId"], {"QueueName": [str]}),
        "send_message": _Op("SendMessage", ["QueueUrl", "MessageBody"], ["QueueUrl", "MessageBody", "DelaySeconds", "MessageAttributes"],
                            ["QueueUrl", "MessageBody", "DelaySeconds", "MessageAttributes", "MessageSystemAttributes",
                             "MessageDeduplicationId", "MessageGroupId"],
                            {"QueueUrl": [str], "MessageBody": [str], "DelaySeconds": [int], "MessageAttributes": [dict]}),
        "receive_message": _Op("ReceiveMessage", ["QueueUrl"], ["QueueUrl", "AttributeNames", "MessageSystemAttributeNames",
                                                                 "MessageAttributeNames", "MaxNumberOfMessages", "VisibilityTimeout", "WaitTimeSeconds"],
                               ["QueueUrl", "AttributeNames", "MessageSystemAttributeNames", "MessageAttributeNames",
                                "MaxNumberOfMessages", "VisibilityTimeout", "WaitTimeSeconds", "ReceiveRequestAttemptId"],
                               {"QueueUrl": [str], "AttributeNames": [list, tuple], "MessageSystemAttributeNames": [list, tuple],
                                "MessageAttributeNames": [list, tuple], "MaxNumberOfMessages": [int], "VisibilityTimeout": [int],
                                "WaitTimeSeconds": [int]}),
        "delete_message": _Op("DeleteMessage", ["QueueUrl", "ReceiptHandle"], ["QueueUrl", "ReceiptHandle"], ["QueueUrl", "ReceiptHandle"],
                              {"QueueUrl": [str], "ReceiptHandle": [str]}),
    }

    def _url(self, name):
        return f"https://sqs.{self.meta.region_name}.amazonaws.com/{ACCOUNT}/{name}"

    def _queue(self, url, op):
        if url not in self._c.sqs:
            raise self._error("AWS.SimpleQueueService.NonExistentQueue", "The specified queue does not exist.", op, 400,
                              {"QueryErrorCode": "QueueDoesNotExist", "Type": "Sender"})
        return self._c.sqs[url]

    def _create_queue(self, QueueName, Attributes=None):
        url = self._url(QueueName)
        self._c.sqs.setdefault(url, {"messages": [], "handles": {}, "attributes": {"VisibilityTimeout": "30", **(Attributes or {})}})
        return {"QueueUrl": url}

    def _get_queue_url(self, QueueName):
        url = self._url(QueueName)
        self._queue(url, "GetQueueUrl")
        return {"QueueUrl": url}

    def _send_message(self, QueueUrl, MessageBody, DelaySeconds=0, MessageAttributes=None):
        q = self._queue(QueueUrl, "SendMessage")
        mid = str(_uuid.UUID(int=self._c.rng.getrandbits(128), version=4))
        now = self._c.now_s
        q["messages"].append({"MessageId": mid, "Body": MessageBody, "MessageAttributes": MessageAttributes or {},
                              "ReceiveCount": 0, "visible_at": now + DelaySeconds, "sent": now, "first_receive": None, "handle": None})
        self._c.calls.append(("sqs.send_message", MessageBody))
        return {"MD5OfMessageBody": _hashlib.md5(MessageBody.encode()).hexdigest(), "MessageId": mid}

    def _receive_message(self, QueueUrl, AttributeNames=None, MessageSystemAttributeNames=None, MessageAttributeNames=None,
                         MaxNumberOfMessages=1, VisibilityTimeout=None, WaitTimeSeconds=0):
        q = self._queue(QueueUrl, "ReceiveMessage")
        if not 1 <= MaxNumberOfMessages <= 10:
            raise self._error("InvalidParameterValue", "Value for parameter MaxNumberOfMessages is invalid. Reason: Must be between 1 and 10, if provided.", "ReceiveMessage", 400)
        if not 0 <= WaitTimeSeconds <= 20:
            raise self._error("InvalidParameterValue", "Value for parameter WaitTimeSeconds is invalid. Reason: Must be >= 0 and <= 20, if provided.", "ReceiveMessage", 400)
        vt = VisibilityTimeout if VisibilityTimeout is not None else int(q["attributes"].get("VisibilityTimeout", "30"))
        now = self._c.now_s
        wanted = set(MessageSystemAttributeNames or []) | set(AttributeNames or [])
        out = []
        for m in q["messages"]:
            if len(out) >= MaxNumberOfMessages:
                break
            if m["visible_at"] > now:
                continue
            m["ReceiveCount"] += 1
            m["first_receive"] = m["first_receive"] if m["first_receive"] is not None else now
            m["visible_at"] = now + vt
            handle = _b64.b64encode(f"{m['MessageId']}#{m['ReceiveCount']}".encode()).decode()
            q["handles"][handle] = m["MessageId"]
            m["handle"] = handle
            msg = {"MessageId": m["MessageId"], "ReceiptHandle": handle, "MD5OfBody": _hashlib.md5(m["Body"].encode()).hexdigest(), "Body": m["Body"]}
            if wanted:
                attrs = {"ApproximateReceiveCount": str(m["ReceiveCount"]), "SentTimestamp": str(int(1_790_000_000_000 + m["sent"] * 1000)),
                         "ApproximateFirstReceiveTimestamp": str(int(1_790_000_000_000 + m["first_receive"] * 1000)), "SenderId": "AIDAMOCKSENDER"}
                msg["Attributes"] = attrs if "All" in wanted else {k: v for k, v in attrs.items() if k in wanted}
            if MessageAttributeNames and m["MessageAttributes"]:
                names = set(MessageAttributeNames)
                msg["MessageAttributes"] = {k: v for k, v in m["MessageAttributes"].items() if "All" in names or ".*" in names or k in names}
                msg["MD5OfMessageAttributes"] = _hashlib.md5(_json.dumps(msg["MessageAttributes"], sort_keys=True).encode()).hexdigest()
            out.append(msg)
        self._c.calls.append(("sqs.receive_message", len(out)))
        res = {}
        if out:  # like the real API, "Messages" is missing when nothing was received
            res["Messages"] = out
        return res

    def _delete_message(self, QueueUrl, ReceiptHandle):
        q = self._queue(QueueUrl, "DeleteMessage")
        if ReceiptHandle not in q["handles"]:
            raise self._error("ReceiptHandleIsInvalid", f'The input receipt handle "{ReceiptHandle}" is not a valid receipt handle.', "DeleteMessage", 400,
                              {"QueryErrorCode": "ReceiptHandleIsInvalid", "Type": "Sender"})
        mid = q["handles"][ReceiptHandle]
        q["messages"] = [m for m in q["messages"] if m["MessageId"] != mid]  # a stale handle of a live message also deletes it
        self._c.calls.append(("sqs.delete_message", mid))
        return {}


class SecretsManager(_AwsClient):
    _SERVICE = "secretsmanager"
    _EXCEPTIONS = ("ResourceNotFoundException", "InvalidParameterException", "InvalidRequestException", "DecryptionFailure", "InternalServiceError")
    _OPS = {"get_secret_value": _Op("GetSecretValue", ["SecretId"], ["SecretId"], ["SecretId", "VersionId", "VersionStage"], {"SecretId": [str]})}

    def _get_secret_value(self, SecretId):
        self._c.calls.append(("secretsmanager.get_secret_value", SecretId))
        name = SecretId
        m = _re.match(r"arn:aws:secretsmanager:[\w-]+:\d+:secret:(.+)-\w{6}$", SecretId)
        if m:
            name = m.group(1)
        if name not in self._c.aws_secrets:
            raise self._error("ResourceNotFoundException", "Secrets Manager can't find the specified secret.", "GetSecretValue", 400)
        return {"ARN": f"arn:aws:secretsmanager:{self.meta.region_name}:{ACCOUNT}:secret:{name}-AbCdEf", "Name": name,
                "VersionId": str(_uuid.UUID(bytes=_hashlib.md5(name.encode()).digest(), version=4)), "SecretString": self._c.aws_secrets[name],
                "VersionStages": ["AWSCURRENT"], "CreatedDate": NOW}


def _judge(text):
    """The same keyword rules as the mock DeepSeek server, so answers look familiar."""
    low = text.lower()
    m = _re.search(r"clause\s+(\d+(?:\.\d+)*)", text, _re.I)
    cid = m.group(1) if m else "unknown"
    for kw, verdict, risk in (("unlimited", "redline", "high"), ("any country", "redline", "high"),
                              ("perpetuity", "redline", "medium"), ("without notice", "flag", "medium")):
        if kw in low:
            return {"clause_id": cid, "verdict": verdict, "risk_level": risk}
    return {"clause_id": cid, "verdict": "accept", "risk_level": "low"}


_BEDROCK_MODEL = _re.compile(r"^(arn:aws:bedrock:[\w-]+:\d*:[\w/.-]+|((eu|us|apac|global|jp|au|ca)\.)?(amazon|anthropic|meta|mistral|cohere|ai21|deepseek|openai|qwen|writer|twelvelabs)\.[\w.:-]+)$")
_CONTENT_BLOCK = ["text", "image", "document", "video", "toolUse", "toolResult", "guardContent", "cachePoint", "reasoningContent", "citationsContent"]


class BedrockRuntime(_AwsClient):
    _SERVICE = "bedrock-runtime"
    _EXCEPTIONS = ("AccessDeniedException", "InternalServerException", "ModelErrorException", "ModelNotReadyException",
                   "ModelTimeoutException", "ResourceNotFoundException", "ServiceQuotaExceededException",
                   "ServiceUnavailableException", "ThrottlingException", "ValidationException")
    _OPS = {"converse": _Op("Converse", ["modelId"], ["modelId", "messages", "system", "inferenceConfig"],
                            ["modelId", "messages", "system", "inferenceConfig", "toolConfig", "guardrailConfig",
                             "additionalModelRequestFields", "promptVariables", "additionalModelResponseFieldPaths",
                             "requestMetadata", "performanceConfig"],
                            {"modelId": [str], "messages": [list, tuple], "system": [list, tuple], "inferenceConfig": [dict]}),
            "invoke_model": _Op("InvokeModel", ["modelId"], [], ["body", "contentType", "accept", "modelId", "trace",
                                                                  "guardrailIdentifier", "guardrailVersion", "performanceConfigLatency"])}

    def _validate_nested(self, op_name, kw):
        report = []
        if op_name != "Converse":
            return report
        for i, m in enumerate(kw.get("messages") or []):
            where = f"messages[{i}]"
            if not isinstance(m, dict):
                report.append(f"Invalid type for parameter {where}, value: {m}, type: {type(m)}, valid types: <class 'dict'>")
                continue
            for k in ("role", "content"):
                if k not in m:
                    report.append(f'Missing required parameter in {where}: "{k}"')
            for k in m:
                if k not in ("role", "content"):
                    report.append(f'Unknown parameter in {where}: "{k}", must be one of: role, content')
            content = m.get("content")
            if content is not None and not isinstance(content, (list, tuple)):
                report.append(f"Invalid type for parameter {where}.content, value: {content}, type: {type(content)}, valid types: <class 'list'>, <class 'tuple'>")
                continue
            for j, b in enumerate(content or []):
                if isinstance(b, dict):
                    for k in b:
                        if k not in _CONTENT_BLOCK:
                            report.append(f'Unknown parameter in {where}.content[{j}]: "{k}", must be one of: {", ".join(_CONTENT_BLOCK)}')
        for i, b in enumerate(kw.get("system") or []):
            if isinstance(b, dict):
                for k in b:
                    if k not in ("text", "guardContent", "cachePoint"):
                        report.append(f'Unknown parameter in system[{i}]: "{k}", must be one of: text, guardContent, cachePoint')
        cfg = kw.get("inferenceConfig") or {}
        for k in cfg:
            if k not in ("maxTokens", "temperature", "topP", "stopSequences"):
                report.append(f'Unknown parameter in inferenceConfig: "{k}", must be one of: maxTokens, temperature, topP, stopSequences')
        if isinstance(cfg.get("maxTokens"), int) and cfg["maxTokens"] < 1:
            report.append(f"Invalid value for parameter inferenceConfig.maxTokens, value: {cfg['maxTokens']}, valid min value: 1")
        return report

    def _invoke_model(self, **kw):
        raise NotImplementedError(_tr("本页的模拟只实现了 converse（统一的对话接口）；invoke_model 的请求体格式随模型而变", "this page's simulation only implements converse (the unified chat API); invoke_model's body format differs per model"))

    def _converse(self, modelId, messages=None, system=None, inferenceConfig=None):
        if not _BEDROCK_MODEL.match(modelId):
            raise self._error("ValidationException", "The provided model identifier is invalid.", "Converse")
        messages = list(messages or [])
        for i, m in enumerate(messages):
            for b in m["content"]:
                if "text" not in b:
                    raise NotImplementedError(_tr("本页的模拟 converse 只支持 text 内容块（真 Bedrock 还支持图片、文档、工具调用等）", "this page's simulated converse only supports text content blocks (real Bedrock also takes images, documents, tool calls and more)"))
        if not messages or messages[0]["role"] != "user":
            raise self._error("ValidationException", "A conversation must start with a user message. Try again with a conversation that starts with a user message.", "Converse")
        cfg = inferenceConfig or {}
        for k in ("temperature", "topP"):
            if k in cfg and not 0 <= cfg[k] <= 1:
                raise self._error("ValidationException", f"The value of {k} must be between 0 and 1.", "Converse")
        user_text = " ".join(b["text"] for b in messages[-1]["content"])
        sys_text = " ".join(b.get("text", "") for b in (system or []))
        reply = _json.dumps(_judge(user_text)) if "json" in (sys_text + " " + user_text).lower() else "Mock Bedrock reply: " + user_text[:60]
        in_tokens = len(sys_text + "".join(b["text"] for m in messages for b in m["content"])) // 4 + 5
        out_tokens, stop = len(reply) // 4 + 3, "end_turn"
        if cfg.get("maxTokens") is not None and out_tokens > cfg["maxTokens"]:
            reply, out_tokens, stop = reply[: cfg["maxTokens"] * 4], cfg["maxTokens"], "max_tokens"
        self._c.calls.append(("bedrock.converse", modelId))
        return {"output": {"message": {"role": "assistant", "content": [{"text": reply}]}}, "stopReason": stop,
                "usage": {"inputTokens": in_tokens, "outputTokens": out_tokens, "totalTokens": in_tokens + out_tokens},
                "metrics": {"latencyMs": 420}}


_AWS_CLIENTS = {"s3": S3, "sqs": SQS, "secretsmanager": SecretsManager, "bedrock-runtime": BedrockRuntime}


def _client(service_name, region_name=None, config=None, **kwargs):
    cloud = _cloud()
    cls = _AWS_CLIENTS.get(service_name)
    if cls is None:
        raise NotImplementedError(_tr(f"本页的模拟 boto3 只有 s3、sqs、secretsmanager、bedrock-runtime，没有 {service_name}", f"this page's simulated boto3 only has s3, sqs, secretsmanager and bedrock-runtime, not {service_name}"))
    region = region_name or (config.region_name if config else None) or cloud.aws_region
    if region is None:
        if service_name != "s3":
            raise NoRegionError()
        region = "us-east-1"
    return cls(cloud, region, config)


class Session:
    def __init__(self, region_name=None, profile_name=None, **kwargs):
        self.region_name, self.profile_name = region_name, profile_name

    def client(self, service_name, region_name=None, **kwargs):
        return _client(service_name, region_name=region_name or self.region_name, **kwargs)


def _resource(*a, **kw):
    raise NotImplementedError(_tr("本页的模拟只有 boto3.client(...)，没有 boto3.resource(...)（AWS 已经不再给 resource 接口加新功能）", "this page's simulation only has boto3.client(...), not boto3.resource(...) (AWS no longer adds features to the resource interface)"))


# ======================================================================== Google: api_core exceptions
class GoogleAPIError(Exception):
    """Base of all google.api_core exceptions."""


class GoogleAPICallError(GoogleAPIError):
    code = None

    def __init__(self, message, errors=(), details=(), response=None):
        self.message, self.errors, self.details, self.response = message, list(errors), list(details), response
        super().__init__(message)

    def __str__(self):
        return f"{self.code} {self.message}"


class Redirection(GoogleAPICallError):
    pass


class ClientErrorG(GoogleAPICallError):
    pass


class BadRequest(ClientErrorG):
    code = 400


class InvalidArgument(BadRequest):
    pass


class Unauthorized(ClientErrorG):
    code = 401


class Forbidden(ClientErrorG):
    code = 403


class PermissionDenied(Forbidden):
    pass


class NotFound(ClientErrorG):
    code = 404


class Conflict(ClientErrorG):
    code = 409


class AlreadyExists(Conflict):
    pass


class PreconditionFailed(ClientErrorG):
    code = 412


class TooManyRequests(ClientErrorG):
    code = 429


class ResourceExhausted(TooManyRequests):
    pass


class ServerError(GoogleAPICallError):
    pass


class InternalServerError(ServerError):
    code = 500


class ServiceUnavailable(ServerError):
    code = 503


class GatewayTimeout(ServerError):
    code = 504


class DeadlineExceeded(GatewayTimeout):
    pass


_G_EXC = dict(GoogleAPIError=GoogleAPIError, GoogleAPICallError=GoogleAPICallError, Redirection=Redirection, ClientError=ClientErrorG,
              BadRequest=BadRequest, InvalidArgument=InvalidArgument, Unauthorized=Unauthorized, Forbidden=Forbidden,
              PermissionDenied=PermissionDenied, NotFound=NotFound, Conflict=Conflict, AlreadyExists=AlreadyExists,
              PreconditionFailed=PreconditionFailed, TooManyRequests=TooManyRequests, ResourceExhausted=ResourceExhausted,
              ServerError=ServerError, InternalServerError=InternalServerError, ServiceUnavailable=ServiceUnavailable,
              GatewayTimeout=GatewayTimeout, DeadlineExceeded=DeadlineExceeded)
for _c in (BotoCoreError, NoCredentialsError, NoRegionError, ParamValidationError, ClientError,
           InvalidRetryConfigurationError, InvalidRetryModeError, InvalidMaxRetryAttemptsError):
    _c.__module__ = "botocore.exceptions"
Config.__module__ = "botocore.config"
for _n, _c in _G_EXC.items():
    _c.__module__ = "google.api_core.exceptions"
    _c.__name__ = _c.__qualname__ = _n


# ======================================================================== Google Cloud Storage
class Blob:
    def __init__(self, name, bucket, **kwargs):
        self.name, self.bucket = name, bucket
        self._properties = {}

    def _c(self):
        return _cloud()

    def _store(self, url):
        c = self._c()
        if self.bucket.name not in c.gcs:
            raise NotFound(f"{url}: The specified bucket does not exist.")
        return c.gcs[self.bucket.name]

    def _load(self, o):
        self._properties = {"size": len(o["data"]), "contentType": o["content_type"], "generation": o["generation"],
                            "updated": o["updated"], "md5Hash": _b64.b64encode(_hashlib.md5(o["data"]).digest()).decode(),
                            "metadata": dict(o["metadata"]) or None}

    size = property(lambda self: self._properties.get("size"))
    content_type = property(lambda self: self._properties.get("contentType"))
    generation = property(lambda self: self._properties.get("generation"))
    updated = property(lambda self: self._properties.get("updated"))
    md5_hash = property(lambda self: self._properties.get("md5Hash"))

    @property
    def metadata(self):
        return self._properties.get("metadata")

    @metadata.setter
    def metadata(self, value):
        self._properties["metadata"] = dict(value or {})

    def upload_from_string(self, data, content_type="text/plain", *, if_generation_match=None, **kwargs):
        c = self._c()
        retried = if_generation_match is not None  # uploads are retried only when they are conditional
        c.maybe_fail_google("storage", "upload", retried)
        store = self._store(f"POST https://storage.googleapis.com/upload/storage/v1/b/{self.bucket.name}/o?uploadType=multipart")
        if isinstance(data, str):
            data = data.encode("utf-8")
        elif not isinstance(data, bytes):
            raise TypeError(f"{data!r} could not be converted to bytes")
        if if_generation_match is not None:
            current = store[self.name]["generation"] if self.name in store else 0
            if current != if_generation_match:
                raise PreconditionFailed(f"POST https://storage.googleapis.com/upload/storage/v1/b/{self.bucket.name}/o?uploadType=multipart&ifGenerationMatch={if_generation_match}: At least one of the pre-conditions you specified did not hold.")
        store[self.name] = {"data": data, "content_type": content_type, "generation": next(c.gcs_generation),
                            "updated": c.clock(), "metadata": dict(self._properties.get("metadata") or {})}
        self._load(store[self.name])
        c.calls.append(("gcs.upload", self.bucket.name, self.name))

    def download_as_bytes(self, client=None, start=None, end=None, raw_download=False, **kwargs):
        c = self._c()
        c.maybe_fail_google("storage", "download", True)
        url = f"GET https://storage.googleapis.com/download/storage/v1/b/{self.bucket.name}/o/{_urlparse.quote(self.name, safe='')}?alt=media"
        o = self._store(url).get(self.name)
        c.calls.append(("gcs.download", self.bucket.name, self.name))
        if o is None:
            raise NotFound(f"{url}: No such object: {self.bucket.name}/{self.name}")
        self._load(o)
        return o["data"]

    def download_as_text(self, client=None, start=None, end=None, raw_download=False, encoding=None, **kwargs):
        return self.download_as_bytes().decode(encoding or "utf-8")

    def exists(self, client=None, **kwargs):
        return self.name in self._c().gcs.get(self.bucket.name, {})

    def reload(self, client=None, **kwargs):
        o = self._store(f"GET https://storage.googleapis.com/storage/v1/b/{self.bucket.name}/o/{self.name}").get(self.name)
        if o is None:
            raise NotFound(f"GET https://storage.googleapis.com/storage/v1/b/{self.bucket.name}/o/{_urlparse.quote(self.name, safe='')}: No such object: {self.bucket.name}/{self.name}")
        self._load(o)

    def delete(self, client=None, **kwargs):
        store = self._store(f"DELETE https://storage.googleapis.com/storage/v1/b/{self.bucket.name}/o/{self.name}")
        if self.name not in store:
            raise NotFound(f"DELETE https://storage.googleapis.com/storage/v1/b/{self.bucket.name}/o/{_urlparse.quote(self.name, safe='')}: No such object: {self.bucket.name}/{self.name}")
        del store[self.name]
        self._c().calls.append(("gcs.delete", self.bucket.name, self.name))

    def __repr__(self):
        return f"<Blob: {self.bucket.name}, {self.name}, {self.generation}>"


class Bucket:
    def __init__(self, client, name=None, **kwargs):
        self.client, self.name = client, name
        self._location = None

    @property
    def location(self):
        return _cloud().gcs_locations.get(self.name, self._location)

    @location.setter
    def location(self, value):
        self._location = value

    def blob(self, blob_name, **kwargs):
        return Blob(blob_name, self)

    def get_blob(self, blob_name, client=None, **kwargs):
        blob = Blob(blob_name, self)
        try:
            blob.reload()
        except NotFound:
            return None
        return blob

    def exists(self, client=None, **kwargs):
        return self.name in _cloud().gcs

    def list_blobs(self, max_results=None, page_token=None, prefix=None, delimiter=None, **kwargs):
        return self.client.list_blobs(self, max_results=max_results, page_token=page_token, prefix=prefix, delimiter=delimiter, **kwargs)

    def __repr__(self):
        return f"<Bucket: {self.name}>"


class _BlobIterator:
    """google.api_core.page_iterator.HTTPIterator: lazy, and can only be iterated once."""

    def __init__(self, client, bucket, prefix, delimiter, max_results):
        self._args = (client, bucket, prefix, delimiter, max_results)
        self._started = False
        self.prefixes = set()
        self.num_results = 0

    def __iter__(self):
        if self._started:
            raise ValueError("Iterator has already started", self)
        self._started = True
        return self._items()

    def _items(self):
        client, bucket, prefix, delimiter, max_results = self._args
        c = _cloud()
        c.maybe_fail_google("storage", "list", True)
        if bucket.name not in c.gcs:
            raise NotFound(f"GET https://storage.googleapis.com/storage/v1/b/{bucket.name}/o?projection=noAcl&prefix={prefix or ''}&prettyPrint=false: The specified bucket does not exist.")
        c.calls.append(("gcs.list_blobs", bucket.name, prefix))
        for name in sorted(c.gcs[bucket.name]):
            if not name.startswith(prefix or ""):
                continue
            if delimiter:
                cut = name.find(delimiter, len(prefix or ""))
                if cut >= 0:
                    self.prefixes.add(name[:cut + len(delimiter)])
                    continue
            if max_results is not None and self.num_results >= max_results:
                return
            blob = Blob(name, bucket)
            blob._load(c.gcs[bucket.name][name])
            self.num_results += 1
            yield blob


class _StorageClient:
    def __init__(self, project=None, credentials=None, **kwargs):
        _cloud().check_adc()
        self.project = project or PROJECT

    def bucket(self, bucket_name, user_project=None, **kwargs):  # no API call, like the real client
        return Bucket(self, bucket_name)

    def get_bucket(self, bucket_or_name, **kwargs):
        name = getattr(bucket_or_name, "name", bucket_or_name)
        _cloud().maybe_fail_google("storage", "get_bucket", True)
        if name not in _cloud().gcs:
            raise NotFound(f"GET https://storage.googleapis.com/storage/v1/b/{name}?projection=noAcl&prettyPrint=false: The specified bucket does not exist.")
        return Bucket(self, name)

    def lookup_bucket(self, bucket_name, **kwargs):
        try:
            return self.get_bucket(bucket_name)
        except NotFound:
            return None

    def create_bucket(self, bucket_or_name, requester_pays=None, project=None, user_project=None, location=None, **kwargs):
        name = getattr(bucket_or_name, "name", bucket_or_name)
        c = _cloud()
        if name in c.gcs:
            raise Conflict(f"POST https://storage.googleapis.com/storage/v1/b?project={self.project}&prettyPrint=false: Your previous request to create the named bucket succeeded and you already own it.")
        c.gcs[name] = {}
        c.gcs_locations[name] = (location or getattr(bucket_or_name, "_location", None) or "US").upper()
        c.calls.append(("gcs.create_bucket", name))
        return Bucket(self, name)

    def list_blobs(self, bucket_or_name, max_results=None, page_token=None, prefix=None, delimiter=None, **kwargs):
        bucket = bucket_or_name if isinstance(bucket_or_name, Bucket) else Bucket(self, bucket_or_name)
        unsupported = {k: v for k, v in kwargs.items() if v is not None and k in ("start_offset", "end_offset", "include_trailing_delimiter", "versions", "projection", "fields", "match_glob")}
        if unsupported or page_token is not None:
            raise NotImplementedError(_tr(f"本页的模拟 list_blobs 不支持 {sorted(list(unsupported) + (['page_token'] if page_token else []))}", f"this page's simulated list_blobs does not support {sorted(list(unsupported) + (['page_token'] if page_token else []))}"))
        return _BlobIterator(self, bucket, prefix, delimiter, max_results)


# ======================================================================== BigQuery
class ScalarQueryParameter:
    _TYPES = {"STRING", "INT64", "INTEGER", "FLOAT64", "FLOAT", "NUMERIC", "BIGNUMERIC", "BOOL", "BOOLEAN", "TIMESTAMP",
              "DATETIME", "DATE", "TIME", "BYTES"}

    def __init__(self, name, type_, value):
        self.name, self.type_, self.value = name, type_, value

    def __repr__(self):
        return f"ScalarQueryParameter({self.name!r}, {self.type_!r}, {self.value!r})"


class QueryJobConfig:
    _IMPLEMENTED = {"query_parameters", "dry_run", "use_query_cache", "maximum_bytes_billed", "labels", "default_dataset", "use_legacy_sql"}
    _KNOWN = _IMPLEMENTED | {"priority", "destination", "write_disposition", "create_disposition", "job_timeout_ms",
                             "allow_large_results", "clustering_fields", "time_partitioning", "range_partitioning",
                             "table_definitions", "udf_resources", "flatten_results", "schema_update_options",
                             "destination_encryption_configuration", "script_options", "connection_properties",
                             "create_session", "maximum_billing_tier", "reservation"}

    def __init__(self, **kwargs):
        self.query_parameters, self.dry_run, self.use_query_cache = [], None, None
        self.maximum_bytes_billed, self.labels, self.default_dataset, self.use_legacy_sql = None, {}, None, None
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __setattr__(self, name, value):
        if not name.startswith("_"):
            if name not in self._KNOWN:
                raise AttributeError(f"Property {name} is unknown for {type(self)}.")
            if name not in self._IMPLEMENTED and value is not None:
                raise NotImplementedError(_tr(f"本页的模拟不支持 QueryJobConfig 的 {name}（真 SDK 支持）", f"this page's simulation does not support QueryJobConfig.{name} (the real SDK does)"))
            if name == "use_legacy_sql" and value:
                raise NotImplementedError(_tr("本页只有 GoogleSQL（标准 SQL），不支持 legacy SQL", "this page only has GoogleSQL (standard SQL), not legacy SQL"))
        object.__setattr__(self, name, value)


class SchemaField:
    def __init__(self, name, field_type, mode="NULLABLE", default_value_expression=None, description=None, **kwargs):
        self.name, self.field_type, self.mode, self.description = name, field_type, mode, description

    def __repr__(self):
        return f"SchemaField('{self.name}', '{self.field_type}', '{self.mode}', None, None, (), None)"

    def __eq__(self, other):
        return isinstance(other, SchemaField) and (self.name, self.field_type, self.mode) == (other.name, other.field_type, other.mode)


class Row:
    """google.cloud.bigquery.table.Row: row["col"], row.col, row[0], row.get("col"), dict(row.items())."""

    def __init__(self, values, field_to_index):
        self._xxx_values, self._xxx_field_to_index = tuple(values), dict(field_to_index)

    def values(self):
        return self._xxx_values

    def keys(self):
        return self._xxx_field_to_index.keys()

    def items(self):
        for k, i in self._xxx_field_to_index.items():
            yield k, self._xxx_values[i]

    def get(self, key, default=None):
        i = self._xxx_field_to_index.get(key)
        return default if i is None else self._xxx_values[i]

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        i = self._xxx_field_to_index.get(name)
        if i is None:
            raise AttributeError(f"no row field {name!r}")
        return self._xxx_values[i]

    def __getitem__(self, key):
        if isinstance(key, str):
            i = self._xxx_field_to_index.get(key)
            if i is None:
                raise KeyError(f"no row field {key!r}")
            return self._xxx_values[i]
        return self._xxx_values[key]

    def __iter__(self):
        return iter(self._xxx_values)

    def __len__(self):
        return len(self._xxx_values)

    def __eq__(self, other):
        return isinstance(other, Row) and self._xxx_values == other._xxx_values and self._xxx_field_to_index == other._xxx_field_to_index

    def __repr__(self):
        return f"Row({self._xxx_values!r}, {self._xxx_field_to_index!r})"


class RowIterator:
    """Iterate once (a second loop raises ValueError); use list(job.result()) to keep the rows."""

    def __init__(self, rows, schema):
        self._rows, self.schema = rows, schema
        self.total_rows = len(rows)
        self._started = False

    def __iter__(self):
        if self._started:
            raise ValueError("Iterator has already started", self)
        self._started = True
        return iter(self._rows)

    def to_dataframe(self, *a, **kw):
        raise NotImplementedError(_tr("to_dataframe() 需要 pandas，本页没有；在本机 pip install 'google-cloud-bigquery[pandas]' 后可以用", "to_dataframe() needs pandas, which this page does not have; on your own computer, pip install 'google-cloud-bigquery[pandas]'"))


_TS = _re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
_DATE = _re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _bq_value(v):
    """SQLite keeps timestamps as text; BigQuery returns TIMESTAMP as datetime (UTC) and DATE as date."""
    if isinstance(v, str):
        if _TS.match(v):
            return _dt.datetime.fromisoformat(v).replace(tzinfo=_dt.timezone.utc)
        if _DATE.match(v):
            return _dt.date.fromisoformat(v)
    return v


def _bq_type(values):
    kinds = {type(v) for v in values if v is not None}
    if not kinds or kinds == {str}:
        return "STRING"
    if kinds == {_dt.datetime}:
        return "TIMESTAMP"
    if kinds == {_dt.date}:
        return "DATE"
    if kinds == {int}:
        return "INTEGER"
    if kinds <= {int, float}:
        return "FLOAT"
    return "STRING"


class QueryJob:
    def __init__(self, client, sql, config):
        c = client._c
        self.query, self.job_id = sql, str(_uuid.UUID(int=c.rng.getrandbits(128), version=4))
        self.location, self.project = client.location or "EU", client.project
        self.labels = dict(config.labels or {})
        self.dry_run = bool(config.dry_run)
        self.state, self.cache_hit, self.error_result, self.errors = "DONE", False, None, None
        self._error, self._rows = None, None
        self.total_bytes_processed = self.total_bytes_billed = None
        try:
            translated, tables = c.bq_prepare(sql, config)
        except GoogleAPICallError as exc:
            if self.dry_run:        # a dry run reports a bad query right away ...
                raise
            self._error = exc       # ... a real job fails, and result() raises
            self.error_result = exc.errors[0] if exc.errors else {"reason": "invalidQuery", "message": exc.message}
            return
        processed = c.bq_bytes(translated)
        billed = c.bq_billed(processed, len(tables))
        key = (translated, tuple((p.name, p.value) for p in config.query_parameters))
        if self.dry_run:
            c.bq_check_runs(translated, config)               # a dry run validates the query and reports errors now
            self.total_bytes_processed, self.total_bytes_billed = processed, None
            return
        self.total_bytes_processed = processed
        if config.use_query_cache is not False and key in c.bq_cache:
            self.cache_hit, self.total_bytes_processed, self.total_bytes_billed = True, 0, 0
            self._rows = c.bq_cache[key]
            return
        if config.maximum_bytes_billed is not None and billed > int(config.maximum_bytes_billed):
            msg = f"Query exceeded limit for bytes billed: {int(config.maximum_bytes_billed)}. {billed} or higher required."
            self._error = InternalServerError(f"{msg}; reason: bytesBilledLimitExceeded, message: {msg}",
                                              errors=[{"reason": "bytesBilledLimitExceeded", "message": msg}])
            self.error_result = {"reason": "bytesBilledLimitExceeded", "message": msg}
            self.total_bytes_billed = None
            return
        try:
            self._rows = c.bq_run(translated, config)
        except GoogleAPICallError as exc:   # query errors surface from result(), like the real client
            self._error = exc
            self.error_result = exc.errors[0] if exc.errors else {"reason": "invalidQuery", "message": exc.message}
            self.total_bytes_billed = None
            return
        self.total_bytes_billed = billed
        if self._rows[0]:
            c.bq_cache[key] = self._rows

    def done(self, *a, **kw):
        return True

    def result(self, timeout=None, **kwargs):
        if self._error is not None:
            raise self._error
        if self.dry_run:
            return RowIterator([], [])
        columns, rows = self._rows
        index = {col: i for i, col in enumerate(columns)}
        rows = [tuple(_bq_value(v) for v in r) for r in rows]
        schema = [SchemaField(col, _bq_type([r[i] for r in rows])) for i, col in enumerate(columns)]
        return RowIterator([Row(r, index) for r in rows], schema)


class TableReference:
    def __init__(self, project, dataset_id, table_id):
        self.project, self.dataset_id, self.table_id = project, dataset_id, table_id

    def __str__(self):
        return f"{self.project}.{self.dataset_id}.{self.table_id}"


class Table:
    def __init__(self, ref, schema, num_rows, streaming):
        self.reference, self.project, self.dataset_id, self.table_id = ref, ref.project, ref.dataset_id, ref.table_id
        self.full_table_id = f"{ref.project}:{ref.dataset_id}.{ref.table_id}"
        self.schema, self.num_rows = schema, num_rows
        self.streaming_buffer = _types.SimpleNamespace(estimated_rows=streaming) if streaming else None


_TS_COLUMNS = {"created_at": "TIMESTAMP", "uploaded_at": "TIMESTAMP", "signed_up": "DATE"}


class _BigQueryClient:
    def __init__(self, project=None, credentials=None, location=None, default_query_job_config=None, **kwargs):
        self._c = _cloud()
        self._c.check_adc()
        self.project = project or PROJECT
        self.location = location
        self._default_config = default_query_job_config

    def _config(self, job_config):
        if job_config is not None and not isinstance(job_config, QueryJobConfig):
            raise TypeError(f"Expected an instance of QueryJobConfig class for the job_config parameter, but received a value of type {type(job_config)}")
        return job_config or self._default_config or QueryJobConfig()

    def query(self, query, job_config=None, job_id=None, job_id_prefix=None, location=None, project=None, **kwargs):
        self._c.maybe_fail_google("bigquery", "jobs.insert", True)
        self._c.calls.append(("bigquery.query", query))
        return QueryJob(self, query, self._config(job_config))

    def query_and_wait(self, query, *, job_config=None, location=None, project=None, **kwargs):
        return self.query(query, job_config=job_config).result()

    def _ref(self, table):
        if isinstance(table, (Table, TableReference)):
            ref = table if isinstance(table, TableReference) else table.reference
            return ref
        parts = str(table).split(".")
        if len(parts) == 2:
            parts = [self.project] + parts
        if len(parts) != 3:
            raise ValueError(f'table_id must be a fully-qualified ID in standard SQL format, e.g., "project.dataset.table_id", got {table}')
        if parts[1] != "clausecheck":
            raise NotFound(f"Not found: Dataset {parts[0]}:{parts[1]}")
        return TableReference(*parts)

    def _columns(self, ref):
        cols = self._c.db.execute(f"PRAGMA table_info({ref.table_id})").fetchall()
        if not cols:
            raise NotFound(f"Not found: Table {ref.project}:{ref.dataset_id}.{ref.table_id}")
        return cols

    def get_table(self, table, **kwargs):
        ref = self._ref(table)
        cols = self._columns(ref)
        n = self._c.db.execute(f"SELECT COUNT(*) FROM {ref.table_id}").fetchone()[0]
        typ = {"INTEGER": "INTEGER", "REAL": "FLOAT", "TEXT": "STRING"}
        schema = [SchemaField(c[1], _TS_COLUMNS.get(c[1], typ.get(c[2].upper(), "STRING")), "REQUIRED" if c[3] or c[5] else "NULLABLE") for c in cols]
        streaming = self._c.bq_streamed.get(ref.table_id, 0)
        return Table(ref, schema, n - streaming, streaming)

    def insert_rows_json(self, table, json_rows, row_ids=None, skip_invalid_rows=None, ignore_unknown_values=None,
                         template_suffix=None, selected_fields=None, chunk_size=500, timeout=None, **kwargs):
        """Streaming insert: returns [] or a list of {"index", "errors"} for the rows that failed."""
        if not isinstance(json_rows, (list, tuple)):
            raise TypeError("json_rows argument should be a sequence of dicts")
        self._c.maybe_fail_google("bigquery", "insertAll", True)
        ref = self._ref(table)
        cols = {c[1]: c for c in self._columns(ref)}
        errors, good = [], []
        for i, row in enumerate(json_rows):
            problems = []
            if not isinstance(row, dict):
                problems.append({"reason": "invalid", "location": "", "debugInfo": "", "message": "Row must be a JSON object."})
                errors.append({"index": i, "errors": problems})
                continue
            clean = {}
            for k, v in row.items():
                if k not in cols:
                    if not ignore_unknown_values:
                        problems.append({"reason": "invalid", "location": k, "debugInfo": "", "message": f"no such field: {k}."})
                    continue
                decl = cols[k][2].upper()
                bad = (isinstance(v, (dict, list)) or (decl == "INTEGER" and not (isinstance(v, int) or (isinstance(v, str) and v.lstrip("-").isdigit())))
                       or (decl == "REAL" and not (isinstance(v, (int, float)) or (isinstance(v, str) and _re.fullmatch(r"-?\d+(\.\d+)?", v))))
                       or (decl == "TEXT" and not isinstance(v, str)))
                if v is not None and bad:
                    what = "a record" if isinstance(v, dict) else "an array" if isinstance(v, list) else f"a valid {'INT64' if decl == 'INTEGER' else 'FLOAT64' if decl == 'REAL' else 'STRING'}"
                    problems.append({"reason": "invalid", "location": k, "debugInfo": "", "message": f"Cannot convert value to {what.replace('a valid ', '')}: {v!r}." if "valid" in what else f"This field: {k} is not {what}."})
                clean[k] = v
            for k, c in cols.items():  # NOT NULL columns (and the key) are REQUIRED in BigQuery
                if (c[3] or c[5]) and clean.get(k) is None:
                    problems.append({"reason": "invalid", "location": k, "debugInfo": "", "message": f"Missing required field: {k}."})
            if problems:
                errors.append({"index": i, "errors": problems})
            else:
                good.append((i, clean))
        if errors and not skip_invalid_rows:  # the whole request fails; the valid rows are reported as "stopped"
            bad_idx = {e["index"] for e in errors}
            stopped = [{"index": i, "errors": [{"reason": "stopped", "location": "", "debugInfo": "", "message": ""}]} for i, _ in good if i not in bad_idx]
            return sorted(errors + stopped, key=lambda e: e["index"])
        for _, row in good:
            keys = list(row)
            # no primary keys in BigQuery: a row sent twice is stored twice
            self._c.db.execute(f"INSERT INTO {ref.table_id} ({', '.join(keys)}) VALUES ({', '.join('?' for _ in keys)})", [row[k] for k in keys])
        self._c.bq_streamed[ref.table_id] = self._c.bq_streamed.get(ref.table_id, 0) + len(good)
        self._c.bq_cache.clear()
        self._c.calls.append(("bigquery.insert_rows_json", ref.table_id, len(good)))
        return errors


# ======================================================================== Secret Manager
def _crc32c(data):
    crc = 0xFFFFFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
    return crc ^ 0xFFFFFFFF


class _SecretManagerClient:
    def __init__(self, credentials=None, **kwargs):
        _cloud().check_adc()

    @staticmethod
    def secret_version_path(project, secret, secret_version):
        return f"projects/{project}/secrets/{secret}/versions/{secret_version}"

    @staticmethod
    def secret_path(project, secret):
        return f"projects/{project}/secrets/{secret}"

    def access_secret_version(self, request=None, *, name=None, retry=None, timeout=None, metadata=()):
        if request is not None and name is not None:
            raise ValueError("If the `request` argument is set, then none of the individual field arguments should be set.")
        if request is not None:
            name = request.get("name") if isinstance(request, dict) else getattr(request, "name", None)
        c = _cloud()
        c.calls.append(("secretmanager.access_secret_version", name))
        m = _re.fullmatch(r"projects/([^/]+)/secrets/([^/]+)/versions/([^/]+)", name or "")
        if not m:
            raise InvalidArgument("Invalid resource field value in the request.")
        project, secret, version = m.groups()
        if project not in (PROJECT, PROJECT_NUMBER) or secret not in c.gcp_secrets:
            raise NotFound(f"Secret [projects/{PROJECT_NUMBER}/secrets/{secret}] not found or has no versions.")
        if version not in ("latest", "1"):
            raise NotFound(f"Secret Version [projects/{PROJECT_NUMBER}/secrets/{secret}/versions/{version}] not found.")
        data = c.gcp_secrets[secret].encode("utf-8")
        payload = _types.SimpleNamespace(data=data, data_crc32c=_crc32c(data))
        return _types.SimpleNamespace(name=f"projects/{PROJECT_NUMBER}/secrets/{secret}/versions/1", payload=payload)


# ======================================================================== Pub/Sub publisher
class _Future:
    def __init__(self, value=None, error=None):
        self._value, self._error = value, error

    def result(self, timeout=None):
        if self._error is not None:
            raise self._error
        return self._value

    def exception(self, timeout=None):
        return self._error

    def done(self):
        return True

    def add_done_callback(self, fn):
        fn(self)


class PublisherOptions(tuple):
    def __new__(cls, enable_message_ordering=False, flow_control=None, retry=None, timeout=None):
        obj = super().__new__(cls, (enable_message_ordering, flow_control, retry, timeout))
        obj.enable_message_ordering = enable_message_ordering
        return obj


class _PublisherClient:
    def __init__(self, batch_settings=(), publisher_options=(), **kwargs):
        _cloud().check_adc()
        if isinstance(publisher_options, dict):
            ordering = publisher_options.get("enable_message_ordering", False)
        else:
            ordering = getattr(publisher_options, "enable_message_ordering", publisher_options[0] if publisher_options else False)
        self._enable_message_ordering = bool(ordering)

    @staticmethod
    def topic_path(project, topic):
        return f"projects/{project}/topics/{topic}"

    def publish(self, topic, data, ordering_key="", retry=None, timeout=None, **attrs):
        if not isinstance(data, bytes):
            raise TypeError("Data being published to Pub/Sub must be sent as a bytestring.")
        if not self._enable_message_ordering and ordering_key != "":
            raise ValueError("Cannot publish a message with an ordering key when message ordering is not enabled.")
        for k, v in list(attrs.items()):
            if isinstance(v, bytes):
                attrs[k] = v.decode("utf-8")
            elif not isinstance(v, str):
                raise TypeError("All attributes being published to Pub/Sub must be sent as text strings.")
        c = _cloud()
        if topic not in c.topics:  # the error arrives through the future, like the real client
            return _Future(error=NotFound(f"Resource not found (resource={topic.split('/')[-1]})."))
        mid = str(10_000_000_000_000 + next(c.ids))
        c.topics[topic].append({"message_id": mid, "data": data, "attributes": attrs, "ordering_key": ordering_key})
        c.calls.append(("pubsub.publish", topic))
        return _Future(mid)


# ======================================================================== google-genai (Gemini)
class APIError(Exception):
    def __init__(self, code, response_json, response=None):
        err = (response_json or {}).get("error", response_json or {})
        self.code, self.status, self.message = code, err.get("status"), err.get("message")
        self.details, self.response = response_json, response
        super().__init__(f"{self.code} {self.status}. {self.details}")


class GenaiClientError(APIError):
    pass


class GenaiServerError(APIError):
    pass


GenaiClientError.__name__ = GenaiClientError.__qualname__ = "ClientError"
GenaiServerError.__name__ = GenaiServerError.__qualname__ = "ServerError"
for _c in (APIError, GenaiClientError, GenaiServerError):
    _c.__module__ = "google.genai.errors"


class ValidationError(ValueError):
    """What pydantic reports for an unknown field of a google-genai config model."""


_GEN_FIELDS = {"system_instruction", "temperature", "top_p", "top_k", "candidate_count", "max_output_tokens", "stop_sequences",
               "response_logprobs", "logprobs", "presence_penalty", "frequency_penalty", "seed", "response_mime_type",
               "response_schema", "response_json_schema", "routing_config", "model_selection_config", "safety_settings",
               "tools", "tool_config", "labels", "cached_content", "response_modalities", "media_resolution",
               "speech_config", "audio_timestamp", "automatic_function_calling", "thinking_config", "image_config",
               "http_options", "enable_enhanced_civic_answers", "model_armor_config"}
_GEN_IMPLEMENTED = {"system_instruction", "temperature", "max_output_tokens", "response_mime_type", "top_p", "top_k", "seed",
                    "stop_sequences", "candidate_count", "labels", "http_options"}


def _snake(name):
    return _re.sub(r"(?<!^)([A-Z])", r"_\1", name).lower()


class FinishReason(str, _enum.Enum):
    """google.genai.types.FinishReason (the members the mock can produce, plus the common ones)."""
    FINISH_REASON_UNSPECIFIED = "FINISH_REASON_UNSPECIFIED"
    STOP = "STOP"
    MAX_TOKENS = "MAX_TOKENS"
    SAFETY = "SAFETY"
    RECITATION = "RECITATION"
    OTHER = "OTHER"
    MALFORMED_FUNCTION_CALL = "MALFORMED_FUNCTION_CALL"

    @classmethod
    def _missing_(cls, value):  # CaseInSensitiveEnum in the real SDK
        for m in cls:
            if isinstance(value, str) and m.value.lower() == value.lower():
                return m
        return None


FinishReason.__module__ = "google.genai.types"


class GenerateContentConfig:
    def __init__(self, **kwargs):
        values = {}
        for k, v in kwargs.items():
            field = k if k in _GEN_FIELDS else _snake(k)
            if field not in _GEN_FIELDS:
                raise ValidationError(f"1 validation error for GenerateContentConfig\n{k}\n  Extra inputs are not permitted [type=extra_forbidden, input_value={v!r}, input_type={type(v).__name__}]")
            if field not in _GEN_IMPLEMENTED and v is not None:
                raise NotImplementedError(_tr(f"本页的模拟不支持 GenerateContentConfig 的 {field}（真 SDK 支持）", f"this page's simulation does not support GenerateContentConfig.{field} (the real SDK does)"))
            values[field] = v
        for f in _GEN_FIELDS:
            object.__setattr__(self, f, values.get(f))

    def __repr__(self):
        return "GenerateContentConfig(" + ", ".join(f"{k}={v!r}" for k, v in sorted(self.__dict__.items()) if v is not None) + ")"


class _Models:
    def generate_content(self, *, model, contents, config=None):
        c = _cloud()
        c.maybe_fail_genai()
        if not _re.fullmatch(r"(publishers/google/models/)?gemini-[\w.-]+", model):
            raise GenaiClientError(404, {"error": {"code": 404, "message": f"Publisher Model `projects/{PROJECT}/locations/global/publishers/google/models/{model}` was not found or your project does not have access to it.", "status": "NOT_FOUND"}})
        if isinstance(config, dict):
            config = GenerateContentConfig(**config)
        config = config or GenerateContentConfig()
        if isinstance(contents, str):
            text = contents
        elif isinstance(contents, list) and all(isinstance(x, str) for x in contents):
            text = " ".join(contents)
        else:
            raise NotImplementedError(_tr("本页的模拟 generate_content 只接受字符串（或字符串列表）作为 contents", "this page's simulated generate_content only takes a string (or a list of strings) as contents"))
        system = config.system_instruction if isinstance(config.system_instruction, str) else ""
        reply = _json.dumps(_judge(text)) if config.response_mime_type == "application/json" else "Mock Gemini reply: " + text[:60]
        out, finish = len(reply) // 4 + 2, "STOP"
        if config.max_output_tokens is not None and out > config.max_output_tokens:
            reply, out, finish = reply[: config.max_output_tokens * 4], config.max_output_tokens, "MAX_TOKENS"
        prompt = len(system + text) // 4 + 4
        c.calls.append(("genai.generate_content", model))
        usage = _types.SimpleNamespace(prompt_token_count=prompt, candidates_token_count=out, total_token_count=prompt + out,
                                       thoughts_token_count=None, cached_content_token_count=None)
        candidate = _types.SimpleNamespace(finish_reason=FinishReason(finish), content=_types.SimpleNamespace(role="model", parts=[_types.SimpleNamespace(text=reply)]))
        return _types.SimpleNamespace(text=reply, usage_metadata=usage, candidates=[candidate], parsed=None, model_version=model)


class _GenaiClient:
    def __init__(self, *, enterprise=None, vertexai=None, api_key=None, credentials=None, project=None, location=None, http_options=None, **kwargs):
        if enterprise is not None and vertexai is not None and bool(enterprise) != bool(vertexai):
            raise ValueError("enterprise and vertexai must not conflict")
        use_vertex = bool(enterprise if enterprise is not None else vertexai)
        c = _cloud()
        if use_vertex:
            project = project or (PROJECT if c.gcp_adc else None)
            if not project and not api_key:
                raise ValueError("Project or API key must be set when using the Vertex AI API.")
            location = location or "global"
        elif not api_key:
            raise ValueError("No API key was provided.")
        self.vertexai, self.project, self.location = use_vertex, project, location
        self.models = _Models()


# ======================================================================== state + install
class _Cloud:
    """Everything the fake cloud holds. Tests use CLOUD to set up and inspect state."""

    def __init__(self, dataset_sql=""):
        self.ids = _itertools.count(1)
        self.rng = _random.Random(20260923)
        self.calls = []
        self.queue = []                    # (service, error) pairs for fail_next
        self.now_s = 0.0                   # fake clock for SQS visibility timeouts
        self.aws_credentials = True
        self.aws_region = REGION           # the default region from your AWS config
        self.gcp_adc = True                # Application Default Credentials are set up
        self.s3 = {"clausecheck-contracts": {}, "clausecheck-reports": {}}
        self.s3_tokens = {}
        self.sqs = {}
        self.aws_secrets = {"clausecheck/deepseek": _json.dumps({"api_key": "sk-mock-0000"})}
        self.gcs = {"clausecheck-contracts": {}, "clausecheck-reports": {}}
        self.gcs_locations = {"clausecheck-contracts": "EUROPE-NORTH1", "clausecheck-reports": "EUROPE-NORTH1"}
        self.gcs_generation = _itertools.count(1_790_000_000_000_001)
        self.gcp_secrets = {"deepseek-api-key": "sk-mock-0000"}
        self.topics = {f"projects/{PROJECT}/topics/contract-uploaded": []}
        import _ccsql
        self._sql = _ccsql
        self.db = _sqlite3.connect(":memory:")
        _ccsql.bq_register(self.db)
        if dataset_sql:
            self.db.executescript(_re.sub(r"\bINTEGER PRIMARY KEY\b", "INTEGER NOT NULL", dataset_sql))
        self.bq_cache, self.bq_streamed = {}, {}

    # ---- helpers for tests
    def fail_next(self, service, error="throttle", times=1):
        """Queue transient failures. service: s3 / bedrock-runtime / storage / bigquery / genai;
        error: throttle / unavailable. Real SDKs retry some of these by themselves (see maybe_fail)."""
        self.queue.extend([(service, error)] * times)

    def advance(self, seconds):
        self.now_s += seconds

    def clock(self):
        return NOW + _dt.timedelta(seconds=len(self.calls) + self.now_s)

    def request_id(self):
        return _uuid.UUID(int=self.rng.getrandbits(128), version=4).hex.upper()[:16]

    # ---- SDK behaviour
    def sign(self):
        if not self.aws_credentials:
            raise NoCredentialsError()

    def check_adc(self):
        if not self.gcp_adc:
            raise _module_exc("google.auth.exceptions", "DefaultCredentialsError")(
                "Your default credentials were not found. To set up Application Default Credentials, see https://cloud.google.com/docs/authentication/external/set-up-adc for more information.")

    def _take(self, service, limit):
        n = 0
        while self.queue and self.queue[0][0] == service and n < limit:
            kind = self.queue.pop(0)[1]
            n += 1
        return n, (kind if n else None)

    def maybe_fail(self, service, client, op, attempts):
        """boto3 retries throttling / 5xx itself: only `attempts` failures in a row reach your code."""
        if not (self.queue and self.queue[0][0] == service):
            return 0
        n, kind = self._take(service, attempts)
        if n < attempts:
            return n                      # retried behind the scenes; RetryAttempts shows how often
        if service == "s3":
            code, status = ("SlowDown", 503) if kind == "throttle" else ("ServiceUnavailable", 503)
            msg = "Please reduce your request rate." if kind == "throttle" else "Service is unable to handle request."
        else:
            code, status = ("ThrottlingException", 429) if kind == "throttle" else ("ServiceUnavailableException", 503)
            msg = "Too many requests, please wait before trying again." if kind == "throttle" else "The service is unavailable. Try again later."
        raise client._error(code, msg, op, status, retries=attempts - 1, max_reached=True)

    def maybe_fail_google(self, service, op, retried):
        """google-cloud clients retry idempotent calls (and conditional uploads) on 429 / 5xx."""
        if not (self.queue and self.queue[0][0] == service):
            return
        limit = 6 if retried else 1
        n, kind = self._take(service, limit)
        if n < limit:
            return
        raise (TooManyRequests if kind == "throttle" else ServiceUnavailable)(
            f"{op}: {'Rate limit exceeded' if kind == 'throttle' else 'The service is currently unavailable.'}")

    def maybe_fail_genai(self):
        """google-genai does not retry by default: every queued failure reaches your code."""
        if self.queue and self.queue[0][0] == "genai":
            kind = self.queue.pop(0)[1]
            if kind == "throttle":
                raise GenaiClientError(429, {"error": {"code": 429, "message": "Resource exhausted. Please try again later.", "status": "RESOURCE_EXHAUSTED"}})
            raise GenaiServerError(503, {"error": {"code": 503, "message": "The model is overloaded. Please try again later.", "status": "UNAVAILABLE"}})

    # ---- BigQuery on SQLite
    def bq_prepare(self, sql, config):
        if not isinstance(sql, str) or not sql.strip():
            raise BadRequest("Syntax error: Unexpected end of script at [1:1]")
        for name in _re.findall(r"@(\w+)", sql):
            if name not in {p.name for p in config.query_parameters}:
                raise BadRequest(f"Query parameter '{name}' not found at [1:1]")
        for p in config.query_parameters:
            if not isinstance(p, ScalarQueryParameter):
                raise NotImplementedError(_tr("本页的模拟只支持 ScalarQueryParameter", "this page's simulation only supports ScalarQueryParameter"))
            if str(p.type_).upper() not in ScalarQueryParameter._TYPES:
                raise BadRequest(f"Invalid query parameter type: {p.type_}")
        tables = self._sql.table_names(self.db)
        dd = config.default_dataset
        dd = str(getattr(dd, "dataset_id", dd)) if dd else None
        try:
            translated = self._sql.bq_translate(sql, tables, default_dataset=dd)
        except self._sql.BigQueryError as exc:
            raise BadRequest(str(exc), errors=[{"reason": "invalidQuery", "message": str(exc)}])
        used = [t for t in tables if _re.search(r"\b" + t + r"\b", translated)]
        return translated, used

    def _params(self, config):
        values = {}
        for p in config.query_parameters:
            v = p.value
            if isinstance(v, _dt.datetime):
                v = v.astimezone(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if v.tzinfo else v.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(v, _dt.date):
                v = v.isoformat()
            elif isinstance(v, bool):
                v = int(v)
            values[p.name] = v
        return values

    def _sqlite_error(self, exc):
        kept = self._sql.udf_error(exc)
        if kept is not None:
            return BadRequest(str(kept), errors=[{"reason": "invalidQuery", "message": str(kept)}])
        msg = str(exc)
        m = _re.search(r"no such table: (?:\w+\.)?(\w+)", msg)
        if m:
            return NotFound(f"Not found: Table {PROJECT}:clausecheck.{m.group(1)} was not found in location EU",
                            errors=[{"reason": "notFound", "message": msg}])
        return BadRequest(f"Query error: {msg}", errors=[{"reason": "invalidQuery", "message": msg}])

    def bq_check_runs(self, translated, config):
        try:
            self.db.execute("EXPLAIN " + translated, self._params(config))
        except _sqlite3.Error as exc:
            raise self._sqlite_error(exc)

    def bq_run(self, translated, config):
        try:
            cur = self.db.execute(translated, self._params(config))
        except (_sqlite3.Error, self._sql.BigQueryError) as exc:
            raise self._sqlite_error(exc) if isinstance(exc, _sqlite3.Error) else BadRequest(str(exc))
        if cur.description is None:  # DML
            self.db.commit()
            self.bq_cache.clear()
            return [], []
        return [d[0] for d in cur.description], [tuple(r) for r in cur.fetchall()]

    def bq_bytes(self, translated):
        """Bytes a query scans: the full size of every column it mentions, in every table it reads
        (columnar storage). WHERE and LIMIT don't reduce it; SELECT * reads every column."""
        code = _re.sub(r"'(?:[^']|'')*'", "''", translated)
        tables = self._sql.table_names(self.db)
        used = [t for t in tables if _re.search(r"\b" + t + r"\b", code)]
        star = _re.search(r"select\s+(\w+\.)?\*", code, _re.I)
        total = 0
        for t in used:
            for col in [c[1] for c in self.db.execute(f"PRAGMA table_info({t})")]:
                if star or _re.search(r"\b" + col + r"\b", code):
                    if col in _TS_COLUMNS:
                        total += 8 * self.db.execute(f"SELECT COUNT({col}) FROM {t}").fetchone()[0]
                    else:
                        total += self.db.execute(
                            f"SELECT COALESCE(SUM(CASE WHEN typeof({col}) IN ('integer', 'real') THEN 8 "
                            f"WHEN {col} IS NULL THEN 0 ELSE length(CAST({col} AS BLOB)) + 2 END), 0) FROM {t}").fetchone()[0]
        return int(total)

    @staticmethod
    def bq_billed(processed, n_tables):
        """On-demand billing: rounded up to a whole MB, at least 10 MB per table referenced."""
        if processed == 0 and n_tables == 0:
            return 0
        mb = 1024 * 1024
        return max(_math.ceil(processed / mb) * mb, 10 * mb * max(1, n_tables))


def _module_exc(module, name):
    mod = _sys.modules.get(module) or _module(module)
    if not hasattr(mod, name):
        cls = type(name, (Exception,), {"__module__": module})
        setattr(mod, name, cls)
    return getattr(mod, name)


def _cc_cloud_install(dataset_sql=""):
    cloud = _Cloud(dataset_sql)
    _STATE["cloud"] = cloud
    # ---- AWS
    _module("boto3", client=_client, Session=Session, resource=_resource, __version__="1.40.0 (mock)")
    botocore = _module("botocore")
    exc = _module("botocore.exceptions", BotoCoreError=BotoCoreError, ClientError=ClientError, NoCredentialsError=NoCredentialsError,
                  NoRegionError=NoRegionError, ParamValidationError=ParamValidationError,
                  InvalidRetryConfigurationError=InvalidRetryConfigurationError, InvalidRetryModeError=InvalidRetryModeError,
                  InvalidMaxRetryAttemptsError=InvalidMaxRetryAttemptsError)
    cfg = _module("botocore.config", Config=Config)
    botocore.exceptions, botocore.config = exc, cfg
    # ---- Google
    google = _module("google")
    google.__path__ = []
    gcloud = _module("google.cloud")
    gcloud.__path__ = []
    api_core = _module("google.api_core")
    api_core.__path__ = []
    gexc = _module("google.api_core.exceptions", **_G_EXC)
    api_core.exceptions = gexc
    _module("google.cloud.exceptions", **_G_EXC)
    auth = _module("google.auth")
    auth.__path__ = []
    auth.exceptions = _module("google.auth.exceptions")
    _module_exc("google.auth.exceptions", "DefaultCredentialsError")
    storage = _module("google.cloud.storage", Client=_StorageClient, Blob=Blob, Bucket=Bucket)
    bigquery = _module("google.cloud.bigquery", Client=_BigQueryClient, QueryJobConfig=QueryJobConfig, ScalarQueryParameter=ScalarQueryParameter,
                       SchemaField=SchemaField, Row=Row, Table=Table, TableReference=TableReference, QueryJob=QueryJob)
    secretmanager = _module("google.cloud.secretmanager", SecretManagerServiceClient=_SecretManagerClient)
    ptypes = _module("google.cloud.pubsub_v1.types", PublisherOptions=PublisherOptions)
    pubsub = _module("google.cloud.pubsub_v1", PublisherClient=_PublisherClient, types=ptypes)
    pubsub.__path__ = []
    gcloud.storage, gcloud.bigquery, gcloud.secretmanager, gcloud.pubsub_v1 = storage, bigquery, secretmanager, pubsub
    gtypes = _module("google.genai.types", GenerateContentConfig=GenerateContentConfig, FinishReason=FinishReason)
    gerrors = _module("google.genai.errors", APIError=APIError, ClientError=GenaiClientError, ServerError=GenaiServerError)
    genai = _module("google.genai", Client=_GenaiClient, types=gtypes, errors=gerrors)
    genai.__path__ = []
    google.cloud, google.api_core, google.genai, google.auth = gcloud, api_core, genai, auth
    return cloud
