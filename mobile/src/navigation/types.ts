export type RootStackParamList = {
  Intro: undefined;
  Login: undefined;
  Dashboard: undefined;
  NewInspection: undefined;
  CaptureImages: { inspectionId: string; inspectionNumber?: string };
  Analyzing: { inspectionId: string; inspectionNumber?: string };
  ExtractedDeclarations: { inspectionId: string; inspectionNumber?: string };
  Findings: { inspectionId: string; inspectionNumber?: string };
  EvidenceReview: { inspectionId: string; findingId?: string };
  ReviewAndSubmit: { inspectionId: string; inspectionNumber?: string };
  ReportPreview: { inspectionId: string; inspectionNumber?: string };
  ReportsList: undefined;
  Profile: undefined;
  DraftOffline: { clientDraftId?: string } | undefined;
  ListingComparison: { inspectionId: string; inspectionNumber?: string };
};
