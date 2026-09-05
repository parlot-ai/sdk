/**
 * Griffe AST expression formatter and annotation utilities.
 */

export function formatExpr(node: any): string {
  if (node == null) return "";
  if (typeof node === "string") return node;
  if (typeof node === "number" || typeof node === "boolean") return String(node);
  if (Array.isArray(node)) return node.map(formatExpr).join(", ");

  const cls = node.cls;
  switch (cls) {
    case "ExprName":
      return node.name ?? "";
    case "ExprBinOp": {
      const left = formatExpr(node.left);
      const right = formatExpr(node.right);
      return `${left} ${node.operator ?? "|"} ${right}`;
    }
    case "ExprSubscript": {
      const left = formatExpr(node.left);
      const slice = formatExpr(node.slice);
      return `${left}[${slice}]`;
    }
    case "ExprAttribute": {
      if (Array.isArray(node.values)) {
        return node.values.map(formatExpr).join(".");
      }
      const parts = [formatExpr(node.left), formatExpr(node.last ?? node.name)].filter(Boolean);
      return parts.join(".");
    }
    case "ExprTuple": {
      const elts = (node.elements || []).map(formatExpr).join(", ");
      return node.implicit ? elts : `(${elts})`;
    }
    case "ExprList": {
      const elts = (node.elements || []).map(formatExpr).join(", ");
      return `[${elts}]`;
    }
    case "ExprDict": {
      const entries = (node.keys || []).map((k: any, i: number) => {
        const key = formatExpr(k);
        const val = formatExpr(node.values?.[i]);
        return `${key}: ${val}`;
      });
      return `{${entries.join(", ")}}`;
    }
    case "ExprConstant":
      return String(node.value);
    case "ExprKeyword":
      return `${node.name}=${formatExpr(node.value)}`;
    case "ExprVarPositional":
      return `*${formatExpr(node.value)}`;
    case "ExprVarKeyword":
      return `**${formatExpr(node.value)}`;
    case "ExprCall": {
      const fn = formatExpr(node.function);
      const args = (node.arguments || []).map(formatExpr).join(", ");
      return `${fn}(${args})`;
    }
    case "ExprUnaryOp": {
      const op = node.operator ?? "";
      const space = op === "not" ? " " : "";
      return `${op}${space}${formatExpr(node.value)}`;
    }
    default:
      if (node.name) return node.name;
      if (node.value !== undefined) return formatExpr(node.value);
      return "";
  }
}

export function cleanAnn(raw: any): string {
  if (raw == null) return "";
  let text = typeof raw === "string" ? raw : formatExpr(raw);
  text = text.replace(/NoneType/g, "None");
  // Prefer modern union form for readability in docs.
  text = text.replace(/Optional\[([^\]]+)\]/g, "$1 | None");
  // Drop quotes around forward refs / string annotations.
  if (
    text.length >= 2 &&
    (text[0] === "'" || text[0] === '"') &&
    text[text.length - 1] === text[0]
  ) {
    text = text.slice(1, -1);
  }
  return text;
}

export function paramDefault(param: any): string | null {
  if (param.required === true) return null;
  const defaultVal = param.default;
  if (defaultVal === null || defaultVal === undefined) return null;
  let text = typeof defaultVal === "string" ? defaultVal : formatExpr(defaultVal);
  if (text === "" || text === "empty") return null;
  // Normalize string defaults: 'custom' → "custom"
  if (text.length >= 2 && text[0] === "'" && text[text.length - 1] === "'") {
    text = `"${text.slice(1, -1)}"`;
  }
  return text;
}
