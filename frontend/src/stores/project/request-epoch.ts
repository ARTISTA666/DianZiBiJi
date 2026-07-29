// Request-epoch guards shared by all project store slices.
//
// Each epoch is bumped when the selected project changes so that responses
// from a previous project cannot overwrite state that belongs to the newly
// selected one.

export const epochs = {
  session: 0,
  projectData: 0,
  projectDetail: 0,
  ragQuery: 0,
};

export const bumpAllEpochs = () => {
  epochs.projectData += 1;
  epochs.projectDetail += 1;
  epochs.ragQuery += 1;
};

export const resetSessionEpoch = () => {
  epochs.session += 1;
  bumpAllEpochs();
};

export const isCurrentSessionRequest = (requestEpoch: number) =>
  requestEpoch === epochs.session;

export const isCurrentProjectRequest = (
  getState: () => { selectedProjectId: number | null },
  projectId: number | null,
  requestEpoch: number,
): projectId is number => projectId !== null
  && requestEpoch === epochs.projectData
  && getState().selectedProjectId === projectId;
