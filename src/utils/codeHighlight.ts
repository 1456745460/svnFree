import hljs from "highlight.js/lib/core";
import javascript from "highlight.js/lib/languages/javascript";
import typescript from "highlight.js/lib/languages/typescript";
import xml from "highlight.js/lib/languages/xml";
import json from "highlight.js/lib/languages/json";
import css from "highlight.js/lib/languages/css";
import less from "highlight.js/lib/languages/less";
import scss from "highlight.js/lib/languages/scss";
import python from "highlight.js/lib/languages/python";
import rust from "highlight.js/lib/languages/rust";
import java from "highlight.js/lib/languages/java";
import kotlin from "highlight.js/lib/languages/kotlin";
import groovy from "highlight.js/lib/languages/groovy";
import gradle from "highlight.js/lib/languages/gradle";
import go from "highlight.js/lib/languages/go";
import bash from "highlight.js/lib/languages/bash";
import shell from "highlight.js/lib/languages/shell";
import markdown from "highlight.js/lib/languages/markdown";
import sql from "highlight.js/lib/languages/sql";
import yaml from "highlight.js/lib/languages/yaml";
import cpp from "highlight.js/lib/languages/cpp";
import c from "highlight.js/lib/languages/c";
import csharp from "highlight.js/lib/languages/csharp";
import ruby from "highlight.js/lib/languages/ruby";
import php from "highlight.js/lib/languages/php";
import properties from "highlight.js/lib/languages/properties";
import ini from "highlight.js/lib/languages/ini";
import dockerfile from "highlight.js/lib/languages/dockerfile";
import makefile from "highlight.js/lib/languages/makefile";
import nginx from "highlight.js/lib/languages/nginx";
import http from "highlight.js/lib/languages/http";
import diff from "highlight.js/lib/languages/diff";
import dos from "highlight.js/lib/languages/dos";
import powershell from "highlight.js/lib/languages/powershell";
import swift from "highlight.js/lib/languages/swift";
import objectivec from "highlight.js/lib/languages/objectivec";
import scala from "highlight.js/lib/languages/scala";
import lua from "highlight.js/lib/languages/lua";
import perl from "highlight.js/lib/languages/perl";
import r from "highlight.js/lib/languages/r";
import dart from "highlight.js/lib/languages/dart";
import vbnet from "highlight.js/lib/languages/vbnet";
import { escapeHtml, resolveHighlightLang } from "./diffEngine";

let registered = false;

function ensureLanguages() {
  if (registered) return;

  hljs.registerLanguage("javascript", javascript);
  hljs.registerLanguage("typescript", typescript);
  hljs.registerLanguage("xml", xml);
  hljs.registerLanguage("json", json);
  hljs.registerLanguage("css", css);
  hljs.registerLanguage("less", less);
  hljs.registerLanguage("scss", scss);
  hljs.registerLanguage("python", python);
  hljs.registerLanguage("rust", rust);
  hljs.registerLanguage("java", java);
  hljs.registerLanguage("kotlin", kotlin);
  hljs.registerLanguage("groovy", groovy);
  hljs.registerLanguage("gradle", gradle);
  hljs.registerLanguage("go", go);
  hljs.registerLanguage("bash", bash);
  hljs.registerLanguage("shell", shell);
  hljs.registerLanguage("markdown", markdown);
  hljs.registerLanguage("sql", sql);
  hljs.registerLanguage("yaml", yaml);
  hljs.registerLanguage("cpp", cpp);
  hljs.registerLanguage("c", c);
  hljs.registerLanguage("csharp", csharp);
  hljs.registerLanguage("ruby", ruby);
  hljs.registerLanguage("php", php);
  hljs.registerLanguage("properties", properties);
  hljs.registerLanguage("ini", ini);
  hljs.registerLanguage("dockerfile", dockerfile);
  hljs.registerLanguage("makefile", makefile);
  hljs.registerLanguage("nginx", nginx);
  hljs.registerLanguage("http", http);
  hljs.registerLanguage("diff", diff);
  hljs.registerLanguage("dos", dos);
  hljs.registerLanguage("powershell", powershell);
  hljs.registerLanguage("swift", swift);
  hljs.registerLanguage("objectivec", objectivec);
  hljs.registerLanguage("scala", scala);
  hljs.registerLanguage("lua", lua);
  hljs.registerLanguage("perl", perl);
  hljs.registerLanguage("r", r);
  hljs.registerLanguage("dart", dart);
  hljs.registerLanguage("vbnet", vbnet);

  // aliases used by path guessing / DiffViewer / backend
  hljs.registerLanguage("jsx", javascript);
  hljs.registerLanguage("tsx", typescript);
  // FreeMarker / JSP / TLD / Vue SFC: closest practical highlighters
  hljs.registerLanguage("ftl", xml);
  hljs.registerLanguage("jsp", xml);
  hljs.registerLanguage("tld", xml);
  hljs.registerLanguage("vue", xml);
  hljs.registerLanguage("html", xml);
  hljs.registerLanguage("htm", xml);
  hljs.registerLanguage("svg", xml);
  hljs.registerLanguage("pom", xml);
  hljs.registerLanguage("iml", xml);
  hljs.registerLanguage("toml", ini);
  hljs.registerLanguage("conf", ini);
  hljs.registerLanguage("cfg", ini);
  hljs.registerLanguage("env", properties);
  hljs.registerLanguage("bat", dos);
  hljs.registerLanguage("cmd", dos);
  hljs.registerLanguage("ps1", powershell);
  hljs.registerLanguage("m", objectivec);
  hljs.registerLanguage("mm", objectivec);

  registered = true;
}

export function guessLanguageFromPath(path: string): string {
  const base = path.split(/[/\\]/).pop()?.toLowerCase() || "";
  const ext = base.includes(".") ? base.slice(base.lastIndexOf(".") + 1) : "";

  switch (ext) {
    case "js":
    case "mjs":
    case "cjs":
    case "jsx":
      return "javascript";
    case "ts":
    case "tsx":
    case "mts":
    case "cts":
      return "typescript";
    case "vue":
      return "vue";
    case "xml":
    case "xsl":
    case "xslt":
    case "xsd":
    case "wsdl":
    case "plist":
      return "xml";
    case "html":
    case "htm":
    case "xhtml":
      return "html";
    case "svg":
      return "svg";
    // FreeMarker / JSP stack (CCF member project heavy)
    case "ftl":
    case "ftlh":
    case "ftlx":
      return "ftl";
    case "jsp":
    case "jspf":
    case "jspx":
    case "tag":
    case "tagx":
      return "jsp";
    case "tld":
      return "tld";
    case "json":
    case "jsonc":
    case "json5":
      return "json";
    case "md":
    case "markdown":
    case "mdx":
      return "markdown";
    case "py":
    case "pyw":
      return "python";
    case "rs":
      return "rust";
    case "java":
      return "java";
    case "kt":
    case "kts":
      return "kotlin";
    case "groovy":
    case "gvy":
    case "gy":
    case "gsh":
      return "groovy";
    case "gradle":
      return "gradle";
    case "go":
      return "go";
    case "rb":
    case "erb":
      return "ruby";
    case "php":
    case "phtml":
      return "php";
    case "c":
    case "h":
      return "c";
    case "cpp":
    case "cc":
    case "cxx":
    case "hpp":
    case "hh":
    case "hxx":
      return "cpp";
    case "cs":
      return "csharp";
    case "swift":
      return "swift";
    case "m":
    case "mm":
      return "objectivec";
    case "scala":
    case "sc":
      return "scala";
    case "lua":
      return "lua";
    case "pl":
    case "pm":
      return "perl";
    case "r":
      return "r";
    case "dart":
      return "dart";
    case "vb":
    case "vbs":
      return "vbnet";
    case "sh":
    case "bash":
    case "zsh":
    case "ksh":
      return "bash";
    case "shell":
      return "shell";
    case "bat":
    case "cmd":
      return "dos";
    case "ps1":
    case "psm1":
    case "psd1":
      return "powershell";
    case "sql":
    case "ddl":
    case "dml":
      return "sql";
    case "yml":
    case "yaml":
      return "yaml";
    case "toml":
      return "toml";
    case "ini":
    case "cfg":
    case "conf":
      return "ini";
    case "properties":
    case "prop":
      return "properties";
    case "css":
      return "css";
    case "scss":
    case "sass":
      return "scss";
    case "less":
      return "less";
    case "diff":
    case "patch":
      return "diff";
    case "http":
      return "http";
    case "nginx":
      return "nginx";
    case "dockerfile":
      return "dockerfile";
    case "makefile":
    case "mk":
      return "makefile";
    case "iml":
      return "iml";
    case "mf":
      return "properties";
    case "env":
      return "env";
    case "txt":
    case "log":
    case "gitignore":
    case "gitattributes":
    case "editorconfig":
    case "npmrc":
    case "nvmrc":
    case "classpath":
    case "project":
    case "prefs":
    case "bak":
      return "plaintext";
    default:
      break;
  }

  // special filenames without/atypical extensions
  if (base === "dockerfile" || base.startsWith("dockerfile.")) return "dockerfile";
  if (base === "makefile" || base === "gnumakefile") return "makefile";
  if (base === "pom.xml") return "xml";
  if (base === "build.gradle" || base === "settings.gradle") return "gradle";
  if (base === "build.gradle.kts" || base === "settings.gradle.kts") return "kotlin";
  if (base === "cmakelists.txt") return "makefile";
  if (base === "nginx.conf" || base.endsWith(".nginx")) return "nginx";
  if (base === ".env" || base.startsWith(".env.")) return "properties";
  if (base === "manifest.mf") return "properties";
  if (base === "robots.txt" || base === "license" || base === "licence" || base === "readme") {
    return "plaintext";
  }
  if (base.endsWith(".properties.bak") || base.endsWith(".xml.bak")) {
    // fallback for backup text-ish files
    return base.includes(".xml") ? "xml" : "properties";
  }

  return "plaintext";
}

export function highlightCode(code: string, language: string): string {
  ensureLanguages();
  const lang = resolveHighlightLang(language);
  if (!lang || !hljs.getLanguage(lang)) {
    return escapeHtml(code);
  }
  try {
    return hljs.highlight(code, { language: lang, ignoreIllegals: true }).value;
  } catch {
    return escapeHtml(code);
  }
}

export function highlightCodeFromPath(code: string, path: string): string {
  return highlightCode(code, guessLanguageFromPath(path));
}
