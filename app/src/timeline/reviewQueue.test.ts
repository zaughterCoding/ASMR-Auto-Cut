import { describe, expect, it } from "vitest";
import { reviewNeighbor, reviewQueue, reviewStatus } from "./reviewQueue";
import type { SegmentLabel, TimelineSegment } from "../types";

function seg(
  id: string,
  start: number,
  end: number,
  label: SegmentLabel = "uncertain",
): TimelineSegment {
  return {
    id,
    start,
    end,
    label,
    action: "keep",
    confidence: 0.3,
    source: "silero_vad_band",
    edited: false,
  };
}

// 首尾相接铺满 0-60，待听的是 b / d / e 三段
const a = seg("a", 0, 10, "asmr");
const b = seg("b", 10, 20);
const c = seg("c", 20, 30, "asmr");
const d = seg("d", 30, 40);
const e = seg("e", 40, 50);
const f = seg("f", 50, 60, "asmr");
const segments = [a, b, c, d, e, f];

describe("reviewQueue", () => {
  it("keeps only uncertain segments", () => {
    expect(reviewQueue(segments).map((item) => item.id)).toEqual(["b", "d", "e"]);
  });

  it("sorts by time so navigation follows the recording", () => {
    // 队列顺序决定「下一段」往哪走，输入乱序时不能照抄数组顺序
    expect(reviewQueue([e, b, d]).map((item) => item.id)).toEqual(["b", "d", "e"]);
  });

  it("is empty when nothing is left to review", () => {
    expect(reviewQueue([a, c, f])).toEqual([]);
  });
});

describe("reviewNeighbor", () => {
  const queue = reviewQueue(segments);

  it("steps forward and back inside the queue", () => {
    expect(reviewNeighbor(queue, b, 1)?.id).toBe("d");
    expect(reviewNeighbor(queue, d, 1)?.id).toBe("e");
    expect(reviewNeighbor(queue, e, -1)?.id).toBe("d");
    expect(reviewNeighbor(queue, d, -1)?.id).toBe("b");
  });

  it("does not wrap around at either end", () => {
    expect(reviewNeighbor(queue, e, 1)).toBeNull();
    expect(reviewNeighbor(queue, b, -1)).toBeNull();
  });

  it("finds the next queue item after a segment that is not in the queue", () => {
    // 用户从概览点了一段 asmr 在听，下一段待听是它之后的，不是队首
    expect(reviewNeighbor(queue, a, 1)?.id).toBe("b");
    expect(reviewNeighbor(queue, c, 1)?.id).toBe("d");
    expect(reviewNeighbor(queue, f, 1)).toBeNull();
  });

  it("finds the previous queue item before a segment that is not in the queue", () => {
    expect(reviewNeighbor(queue, c, -1)?.id).toBe("b");
    expect(reviewNeighbor(queue, f, -1)?.id).toBe("e");
    expect(reviewNeighbor(queue, a, -1)).toBeNull();
  });

  it("starts at the head when nothing is selected", () => {
    expect(reviewNeighbor(queue, null, 1)?.id).toBe("b");
    // 没有选中项时「上一段」没有起点，交给调用方禁用按钮
    expect(reviewNeighbor(queue, null, -1)).toBeNull();
  });

  it("has nowhere to go with an empty queue", () => {
    expect(reviewNeighbor([], b, 1)).toBeNull();
    expect(reviewNeighbor([], b, -1)).toBeNull();
    expect(reviewNeighbor([], null, 1)).toBeNull();
  });
});

describe("reviewStatus", () => {
  it("reports the position of a segment that is in the queue", () => {
    expect(reviewStatus(segments, d)).toEqual({
      total: 3,
      position: 2,
      prevId: "b",
      nextId: "e",
    });
  });

  it("reports no position for a segment that is not in the queue", () => {
    // 位置是「队列里第几段」，一段 asmr 不属于队列，就不该硬给它编个号
    expect(reviewStatus(segments, c)).toEqual({
      total: 3,
      position: null,
      prevId: "b",
      nextId: "d",
    });
  });

  it("reports the head as the next target when nothing is selected", () => {
    expect(reviewStatus(segments, null)).toEqual({
      total: 3,
      position: null,
      prevId: null,
      nextId: "b",
    });
  });

  it("shrinks the queue as the user re-labels segments", () => {
    // 把 b 判成 talk 之后它当场离队，计数器要跟着掉
    const judged = segments.map((item) => (item.id === "b" ? { ...item, label: "talk" as const } : item));
    expect(reviewStatus(judged, { ...b, label: "talk" })).toEqual({
      total: 2,
      position: null,
      prevId: null,
      nextId: "d",
    });
  });

  it("walks a realistic queue head to tail without skipping or repeating", () => {
    // 上面那些用例都只有三段，测不出「用户到底点不点得完」。复核带在一条 70 分钟
    // 录音上能标出几百段，所以按那个规模铺一遍：300 段待听，每段被一段 asmr 隔开。
    // 从队首一路点「下一段」，走过的必须正好是队列本身——顺序不变、不重不漏，
    // 并且最后一定停下来（不会绕回队首无限转）。
    const many: TimelineSegment[] = [];
    for (let index = 0; index < 300; index += 1) {
      many.push(seg(`k${index}`, index * 10, index * 10 + 1));
      many.push(seg(`s${index}`, index * 10 + 1, index * 10 + 10, "asmr"));
    }

    const walked: string[] = [];
    let current: TimelineSegment | null = null;
    for (let step = 0; step < 1000; step += 1) {
      const { nextId } = reviewStatus(many, current);
      if (nextId === null) break;
      current = many.find((item) => item.id === nextId) ?? null;
      if (current === null) break;
      walked.push(current.id);
    }

    expect(walked).toEqual(reviewQueue(many).map((item) => item.id));
    expect(walked).toHaveLength(300);
    // 走到最后一段之后就没有下一段了，循环是靠 nextId 变 null 退出的
    expect(reviewStatus(many, current).nextId).toBeNull();
  });

  it("disables both directions once the queue is cleared", () => {
    const cleared = segments.map((item) =>
      item.label === "uncertain" ? { ...item, label: "asmr" as const } : item,
    );
    expect(reviewStatus(cleared, a)).toEqual({
      total: 0,
      position: null,
      prevId: null,
      nextId: null,
    });
  });
});
