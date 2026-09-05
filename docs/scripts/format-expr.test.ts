import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanAnn, formatExpr, paramDefault } from "./lib/ast";

describe("formatExpr and cleanAnn", () => {
  test("formats simple identifier", () => {
    const node = { cls: "ExprName", name: "str" };
    expect(cleanAnn(node)).toBe("str");
  });

  test("formats nested unions: TracerProvider | None", () => {
    const node = {
      cls: "ExprBinOp",
      left: { cls: "ExprName", name: "TracerProvider" },
      operator: "|",
      right: "None",
    };
    expect(cleanAnn(node)).toBe("TracerProvider | None");
  });

  test("formats multi-part unions: bool | list[str] | None", () => {
    const node = {
      cls: "ExprBinOp",
      left: {
        cls: "ExprBinOp",
        left: { cls: "ExprName", name: "bool" },
        operator: "|",
        right: {
          cls: "ExprSubscript",
          left: { cls: "ExprName", name: "list" },
          slice: { cls: "ExprName", name: "str" },
        },
      },
      operator: "|",
      right: "None",
    };
    expect(cleanAnn(node)).toBe("bool | list[str] | None");
  });

  test("formats nested subscripts and tuples: list[tuple[str, str, str]]", () => {
    const node = {
      cls: "ExprSubscript",
      left: { cls: "ExprName", name: "list" },
      slice: {
        cls: "ExprSubscript",
        left: { cls: "ExprName", name: "tuple" },
        slice: {
          cls: "ExprTuple",
          elements: [
            { cls: "ExprName", name: "str" },
            { cls: "ExprName", name: "str" },
            { cls: "ExprName", name: "str" },
          ],
          implicit: true,
        },
      },
    };
    expect(cleanAnn(node)).toBe("list[tuple[str, str, str]]");
  });

  test("formats subscripted dicts with unions: dict[str, str] | None", () => {
    const node = {
      cls: "ExprBinOp",
      left: {
        cls: "ExprSubscript",
        left: { cls: "ExprName", name: "dict" },
        slice: {
          cls: "ExprTuple",
          elements: [
            { cls: "ExprName", name: "str" },
            { cls: "ExprName", name: "str" },
          ],
          implicit: true,
        },
      },
      operator: "|",
      right: "None",
    };
    expect(cleanAnn(node)).toBe("dict[str, str] | None");
  });

  test("modernizes Optional[T] into T | None", () => {
    const node = {
      cls: "ExprSubscript",
      left: { cls: "ExprName", name: "Optional" },
      slice: { cls: "ExprName", name: "str" },
    };
    expect(cleanAnn(node)).toBe("str | None");
  });

  test("strips quotes around forward references", () => {
    const node = { cls: "ExprConstant", value: "'LiveKitGenAIProcessor'" };
    expect(cleanAnn(node)).toBe("LiveKitGenAIProcessor");
  });

  test("formats variadic args and kwargs", () => {
    const varPos = { cls: "ExprVarPositional", value: { cls: "ExprName", name: "args" } };
    const varKw = { cls: "ExprVarKeyword", value: { cls: "ExprName", name: "kwargs" } };
    expect(formatExpr(varPos)).toBe("*args");
    expect(formatExpr(varKw)).toBe("**kwargs");
  });
});

describe("paramDefault", () => {
  test("returns null for required parameters", () => {
    expect(paramDefault({ required: true, default: null })).toBeNull();
    expect(paramDefault({ required: false, default: null })).toBeNull();
  });

  test("returns 'None' string for optional parameters with default None", () => {
    expect(paramDefault({ default: "None" })).toBe("None");
  });

  test("normalizes single-quoted string defaults: 'custom' -> \"custom\"", () => {
    expect(paramDefault({ default: "'custom'" })).toBe('"custom"');
    expect(paramDefault({ default: "'completed'" })).toBe('"completed"');
  });

  test("preserves boolean and numeric defaults", () => {
    expect(paramDefault({ default: "False" })).toBe("False");
    expect(paramDefault({ default: "True" })).toBe("True");
    expect(paramDefault({ default: "0" })).toBe("0");
  });
});

describe("live api.json verification", () => {
  const jsonPath = resolve(__dirname, "../../docs-data/api.json");
  const data = JSON.parse(readFileSync(jsonPath, "utf-8"));

  test("resolves ConfigureProtocol.__call__ parameters correctly", () => {
    const proto = data["parlot.core.configure"].members.ConfigureProtocol;
    const call = proto.members.__call__;
    const paramsByName = new Map(call.parameters.map((p: any) => [p.name, p]));

    expect(cleanAnn(paramsByName.get("endpoint").annotation)).toBe("str | None");
    expect(cleanAnn(paramsByName.get("tracer_provider").annotation)).toBe(
      "TracerProvider | None"
    );
    expect(cleanAnn(paramsByName.get("capture_logs").annotation)).toBe(
      "bool | list[str] | None"
    );
    expect(paramDefault(paramsByName.get("endpoint"))).toBe("None");
  });

  test("resolves livekit.configure parameters correctly", () => {
    const lk = data["parlot.instrumentation.livekit._auto"].members.configure;
    const paramsByName = new Map(lk.parameters.map((p: any) => [p.name, p]));

    expect(cleanAnn(paramsByName.get("auto_escalate_sip").annotation)).toBe("bool");
    expect(paramDefault(paramsByName.get("auto_escalate_sip"))).toBe("False");
    expect(cleanAnn(paramsByName.get("escalation_metadata_match").annotation)).toBe(
      "dict[str, str] | None"
    );
    expect(cleanAnn(paramsByName.get("tracer_provider").annotation)).toBe(
      "TracerProvider | None"
    );
  });

  test("resolves langgraph.close_session parameters correctly", () => {
    const close = data["parlot.instrumentation.langgraph._auto"].members.close_session;
    const threadIdParam = close.parameters.find((p: any) => p.name === "thread_id");
    const reasonParam = close.parameters.find((p: any) => p.name === "reason");

    expect(cleanAnn(threadIdParam.annotation)).toBe("str");
    expect(paramDefault(threadIdParam)).toBeNull(); // required!
    expect(cleanAnn(reasonParam.annotation)).toBe("str");
    expect(paramDefault(reasonParam)).toBe('"completed"');
  });

  test("resolves core.platform_refs parameters correctly", () => {
    const stamp = data["parlot.core.platform_refs"].members.stamp_platform_refs;
    const refsParam = stamp.parameters.find((p: any) => p.name === "refs");
    expect(cleanAnn(refsParam.annotation)).toBe("list[tuple[str, str, str]]");

    const addRef = data["parlot.core.platform_refs"].members.add_platform_ref;
    const fwParam = addRef.parameters.find((p: any) => p.name === "framework");
    expect(paramDefault(fwParam)).toBe('"custom"');
  });
});
