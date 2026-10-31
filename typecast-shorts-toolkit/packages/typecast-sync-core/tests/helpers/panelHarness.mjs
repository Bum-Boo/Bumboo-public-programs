// Test-only harnesses that load the parser code embedded in the Adobe panels
// into a Node vm context. They replace host objects (ExtendScript File/Folder,
// UXP storage, Premiere DOM, document) with small fakes backed by the local
// filesystem. They exercise the panels' own parsing/job-discovery JavaScript;
// they do NOT run After Effects or Premiere Pro and prove nothing about the
// Adobe host APIs (footage import, layers, caption tracks).
import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
export const toolkitRoot = join(here, "..", "..", "..", "..");
const aeGeneratorPath = join(toolkitRoot, "apps", "after-effects-typecast-sync", "src", "aeCaptionGenerator.jsx");
const premiereMainPath = join(toolkitRoot, "apps", "premiere-typecast-sync", "src", "main.js");

/** Loads aeCaptionGenerator.jsx with a minimal ExtendScript File/Folder shim and returns TCSS_AE. */
export function loadAeParser() {
  class File {
    constructor(path) {
      this.fsName = path;
      this.name = basename(path);
      this.encoding = "BINARY";
      this._text = null;
    }
    open(mode) {
      if (mode !== "r") {
        return false;
      }
      try {
        this._text = readFileSync(this.fsName, "utf8");
        return true;
      } catch {
        return false;
      }
    }
    read() {
      return this._text;
    }
    close() {
      this._text = null;
    }
  }

  class Folder {
    constructor(path) {
      this.fsName = path;
      this.name = basename(path);
    }
    getFiles() {
      return readdirSync(this.fsName).map((entry) => {
        const full = join(this.fsName, entry);
        return statSync(full).isDirectory() ? new Folder(full) : new File(full);
      });
    }
  }

  const context = vm.createContext({ File, Folder });
  vm.runInContext(readFileSync(aeGeneratorPath, "utf8"), context, { filename: aeGeneratorPath });
  return { TCSS_AE: context.TCSS_AE, File, Folder };
}

/**
 * Loads the Premiere UXP panel main.js with fake `uxp`, `premierepro` and `document`.
 * `folderPath` is what the fake folder picker returns. `project` is what
 * Project.getActiveProject() resolves to (null simulates "no project").
 */
export function loadPremierePanel({ folderPath, project = null }) {
  const elements = {};
  const element = (id) => {
    if (!elements[id]) {
      const listeners = {};
      elements[id] = {
        id,
        textContent: "",
        disabled: id === "generate",
        listeners,
        addEventListener(type, handler) {
          listeners[type] = handler;
        }
      };
    }
    return elements[id];
  };

  const documentListeners = {};
  const document = {
    getElementById: element,
    addEventListener(type, handler) {
      documentListeners[type] = handler;
    }
  };

  const fileEntry = (path) => ({
    isFile: true,
    name: basename(path),
    nativePath: path,
    async read() {
      return readFileSync(path, "utf8");
    },
    async write(contents) {
      writeFileSync(path, contents, "utf8");
    }
  });

  const folderEntry = (path) => ({
    isFile: false,
    name: basename(path),
    nativePath: path,
    async getEntries() {
      return readdirSync(path).map((entry) => {
        const full = join(path, entry);
        return statSync(full).isDirectory() ? folderEntry(full) : fileEntry(full);
      });
    },
    async createFile(name) {
      const full = join(path, name);
      writeFileSync(full, "", "utf8");
      return fileEntry(full);
    }
  });

  const uxp = {
    entrypoints: { setup() {} },
    storage: {
      formats: { utf8: "utf8" },
      localFileSystem: {
        async getFolder() {
          return folderPath ? folderEntry(folderPath) : null;
        },
        getNativePath(entry) {
          return entry.nativePath;
        }
      }
    }
  };

  const premierepro = {
    Project: {
      async getActiveProject() {
        return project;
      }
    }
  };

  const require = (name) => {
    if (name === "uxp") return uxp;
    if (name === "premierepro") return premierepro;
    throw new Error(`Unexpected require(${name}) in Premiere panel test harness`);
  };

  const context = vm.createContext({ require, document });
  vm.runInContext(readFileSync(premiereMainPath, "utf8"), context, { filename: premiereMainPath });

  return {
    elements,
    async start() {
      documentListeners.DOMContentLoaded();
      // The panel fires refreshActiveSequence() without awaiting it; let it settle.
      await new Promise((resolve) => setImmediate(resolve));
    },
    async click(id) {
      await elements[id].listeners.click();
    },
    status() {
      return elements.status.textContent;
    }
  };
}
