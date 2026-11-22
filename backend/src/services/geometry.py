from math import hypot

def bounds(points):
    xs = [p["x"] for p in points]; ys = [p["y"] for p in points]
    return {"min_x": min(xs), "max_x": max(xs), "min_y": min(ys), "max_y": max(ys)}

def overlaps(a, b):
    return not (a["max_x"] < b["min_x"] or a["min_x"] > b["max_x"] or a["max_y"] < b["min_y"] or a["min_y"] > b["max_y"])

def distance(a, b):
    return hypot(a["x"] - b["x"], a["y"] - b["y"])
