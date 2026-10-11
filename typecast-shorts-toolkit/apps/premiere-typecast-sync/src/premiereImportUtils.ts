type UxpLocalFileSystem = {
  getNativePath(entry: unknown): string;
};

type PremiereProject = {
  getActiveSequence(): Promise<{ name: string } | null>;
  getInsertionBin?(): Promise<unknown>;
  getRootItem(): Promise<unknown>;
  importFiles(paths: string[], suppressUI: boolean, targetBin: unknown, asNumberedStills: boolean): Promise<boolean>;
};

type PremiereApi = {
  Project: {
    getActiveProject(): Promise<PremiereProject | null>;
  };
};

export async function getActiveSequenceName(premiere: PremiereApi): Promise<string> {
  const project = await premiere.Project.getActiveProject();
  const sequence = project ? await project.getActiveSequence() : null;
  return sequence ? sequence.name : "No active sequence";
}

export async function importAudioAndSrt(
  premiere: PremiereApi,
  localFileSystem: UxpLocalFileSystem,
  audioEntry: unknown,
  srtEntry: unknown
): Promise<boolean> {
  const project = await premiere.Project.getActiveProject();

  if (!project) {
    throw new Error("No active Premiere Pro project.");
  }

  const targetBin = project.getInsertionBin ? await project.getInsertionBin() : await project.getRootItem();
  const importPaths = [
    localFileSystem.getNativePath(audioEntry),
    localFileSystem.getNativePath(srtEntry)
  ];

  return project.importFiles(importPaths, true, targetBin, false);
}
