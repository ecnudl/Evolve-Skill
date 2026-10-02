"""Read-only KOR native-resource handoff checks, not a correctness/Skill gate.

Caller must first verify sealed report/prediction/plan identities. Missing
cleanup evidence blocks a handoff even if a historical reason suggests cleanup
probably happened. This never relabels scores or starts/stops a container.
"""
from skillopt.continual_eval.core import require


def check_kor_native_handoff(score, prediction, image):
    require(type(score) is dict and type(prediction) is dict and type(image) is str,
            "Invalid handoff evidence types")
    require(type(score.get("status")) is str and type(prediction.get("status")) is str
            and score["status"] in {"pass", "fail", "unknown"}
            and prediction["status"] in {"available", "unknown"}, "Invalid handoff statuses")
    if prediction["status"] == "unknown":
        require(score["status"] == "unknown" and type(prediction.get("reason")) is str
                and score.get("reason") == prediction["reason"]
                and not {"execution_costs", "runtime_image_id", "cleanup_confirmed"} & set(score),
                "Delivery unknown unexpectedly has native execution or changed reason")
        return "delivery_unknown_no_container"
    costs = score.get("execution_costs")
    require(type(costs) is dict and type(costs.get("container_calls")) is int
            and costs["container_calls"] in {0, 1}, "Explicit bounded native execution count required")
    if costs["container_calls"] == 0:
        require(score["status"] == "unknown" and not {"runtime_image_id", "cleanup_confirmed"} & set(score)
                and "image_id" not in costs, "Zero-container receipt contradicts execution evidence")
        return "pre_execution_unknown_no_container"
    require(score.get("cleanup_confirmed") is True and score.get("runtime_image_id") == image
            and costs.get("image_id") == image, "Native cleanup/image evidence missing or mismatched")
    return "native_execution_cleanup_confirmed"
