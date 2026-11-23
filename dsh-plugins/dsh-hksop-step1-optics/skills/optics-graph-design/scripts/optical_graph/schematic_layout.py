"""Port-oriented logical grid and obstacle-aware Manhattan routing (drawing space only)."""
from collections import defaultdict
from dataclasses import dataclass
import heapq
from itertools import count

from .schema import SOURCES, Four, REFLECT, TRANSMIT

STEP, COL, ROW = 16, 176, 144
VECTORS = ((1, 0), (0, 1), (-1, 0), (0, -1))
PORT_SIDE = {"front": 0, "a": 2, "b": 0, "p1": 2, "p2": 3, "p3": 0, "p4": 1}


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    def intersects(self, other, gap=0):
        return (self.x < other.x + other.w + gap and other.x < self.x + self.w + gap
                and self.y < other.y + other.h + gap and other.y < self.y + self.h + gap)

    def contains(self, p):
        return self.x <= p[0] <= self.x + self.w and self.y <= p[1] <= self.y + self.h


@dataclass(frozen=True)
class Place:
    x: int
    y: int
    rotation: int

    def side(self, pin):
        return (PORT_SIDE[pin] + self.rotation) % 4

    def port(self, pin, distance=32):
        dx, dy = VECTORS[self.side(pin)]
        return self.x + distance*dx, self.y + distance*dy

    def boxes(self):
        return (Rect(self.x-31, self.y-31, 62, 62), Rect(self.x+14, self.y-68, 126, 34))


def _position(graph):
    places, occupied = {}, set()
    roots = sorted(graph.nodes, key=lambda n: -getattr(graph.nodes[n], "power_mw", -1)
                   if isinstance(graph.nodes[n], SOURCES) else 2)
    for root in roots:
        if root in places:
            continue
        y = max((p.y for p in places.values()), default=-2*ROW) + 2*ROW
        stack = [(root, None, 0, y, 0, 0)]
        while stack:
            key, incoming, x, y, rotation, grow = stack.pop()
            if key in places:
                continue
            dx, dy = VECTORS[grow]
            while (x, y) in occupied:
                x += dx*COL
                y += dy*ROW
            loc = places[key] = Place(x, y, rotation)
            occupied.add((x, y))
            c = graph.nodes[key]
            pins = list(c.ports)
            if isinstance(c, Four) and incoming is not None:
                pins = list(dict.fromkeys([TRANSMIT[incoming], REFLECT[incoming], *pins]))
            for pin in reversed(pins):
                if pin == incoming:
                    continue
                end = f"{key}.{pin}"
                link = graph._by_port.get(end)
                if link is None:
                    continue
                other, other_pin = link.other(end).split(".")
                side = loc.side(pin)
                vx, vy = VECTORS[side]
                turn = (side+2-PORT_SIDE[other_pin]) % 4
                stack.append((other, other_pin, x+vx*COL, y+vy*ROW, turn, side))
    return places


def _compact(points):
    result = []
    for p in points:
        if result and p == result[-1]:
            continue
        if len(result) >= 2:
            a, b = result[-2:]
            if (a[0] == b[0] == p[0]) or (a[1] == b[1] == p[1]):
                result.pop()
        result.append(p)
    return result


def _route(a, b, places, obstacles, used, tracks):
    n1, p1 = a.split(".")
    n2, p2 = b.split(".")
    u, v = places[n1], places[n2]
    start, goal = u.port(p1, 48), v.port(p2, 48)
    first = (*start, u.side(p1))
    serial = count()
    heap = [(0, next(serial), 0, first)]
    cost, prev = {first: 0}, {}
    x0 = min(r.x for r in obstacles)-8*STEP
    x1 = max(r.x+r.w for r in obstacles)+8*STEP
    y0 = min(r.y for r in obstacles)-8*STEP
    y1 = max(r.y+r.h for r in obstacles)+8*STEP
    blocked = {}

    def clear(point):
        if point not in blocked:
            blocked[point] = not any(r.contains(point) for r in obstacles)
        return blocked[point]

    while heap:
        _, _, price, state = heapq.heappop(heap)
        if price != cost[state]:
            continue
        x, y, direction = state
        if (x, y) == goal:
            pixels = []
            while state is not None:
                pixels.append(state[:2])
                state = prev.get(state)
            points = [u.port(p1), *reversed(pixels), v.port(p2)]
            for h, j in zip(points, points[1:]):
                used.add(tuple(sorted((h, j))))
                axis = 0 if h[1] == j[1] else 1
                tracks[h].add(axis)
                tracks[j].add(axis)
            return _compact(points)
        for nd, (dx, dy) in enumerate(VECTORS):
            point = (x+STEP*dx, y+STEP*dy)
            if nd == (direction+2) % 4 or not (x0 <= point[0] <= x1 and y0 <= point[1] <= y1):
                continue
            if not clear(point) or not clear((x+STEP*dx/2, y+STEP*dy/2)):
                continue
            if point == goal and nd == v.side(p2):
                continue
            edge = tuple(sorted(((x, y), point)))
            charge = 1 + (2.5 if nd != direction else 0) + (22 if edge in used else 0)
            if (1 - nd % 2) in tracks.get(point, ()):
                charge += 3
            total = price + charge
            new = (*point, nd)
            if total < cost.get(new, float("inf")):
                prev[new], cost[new] = (x, y, direction), total
                remaining = (abs(point[0]-goal[0]) + abs(point[1]-goal[1])) / STEP
                heapq.heappush(heap, (total+remaining, next(serial), total, new))
    raise ValueError(f"cannot connect {a} to {b} around diagram symbols")


def segment_box(a, b, pad=3):
    return Rect(min(a[0], b[0])-pad, min(a[1], b[1])-pad, abs(a[0]-b[0])+2*pad, abs(a[1]-b[1])+2*pad)


@dataclass
class Layout:
    places: dict
    routes: dict
    obstacles: list

    def badge(self, route, width, height, reserved, strokes):
        segments = sorted(zip(route, route[1:]), key=lambda s: -sum(abs(a-b) for a, b in zip(*s)))
        for a, b in segments:
            horizontal = a[1] == b[1]
            for f in (.5, .35, .65, .2, .8):
                x, y = (a[0]+f*(b[0]-a[0]), a[1]+f*(b[1]-a[1]))
                for gap in (13, 26, 42, 60, 80, 104, 132, 160):
                    for sign in (-1, 1):
                        if horizontal:
                            box = Rect(x-width/2, y-gap-height if sign < 0 else y+gap, width, height)
                        else:
                            box = Rect(x-gap-width if sign < 0 else x+gap, y-height/2, width, height)
                        if not any(box.intersects(r, 3) for r in reserved) and not any(box.intersects(r) for r in strokes):
                            reserved.append(box)
                            return box, (x, y)
        # Crowded loop: put the annotation into the nearest free perimeter lane.
        x, y = segments[0][0]
        left = min(r.x for r in reserved) - width - 20
        box = Rect(left, y-height/2, width, height)
        while any(box.intersects(r, 5) for r in reserved+strokes):
            box = Rect(box.x, box.y+height+10, width, height)
        reserved.append(box)
        return box, (x, y)


def schematic_layout(graph):
    places = _position(graph)
    obstacles = [box for place in places.values() for box in place.boxes()]
    used, tracks, routes = set(), defaultdict(set), {}
    # Route short, straight connections first, then the spanning-tree closure edges.
    def distance(link):
        u = places[link.u.split(".")[0]]
        v = places[link.v.split(".")[0]]
        return abs(u.x-v.x)+abs(u.y-v.y)
    for link in sorted(graph.links, key=distance):
        routes[link.id] = _route(link.u, link.v, places, obstacles, used, tracks)
    return Layout(places, routes, obstacles)
