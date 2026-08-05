import { NationalDecision } from './NationalDecision.js';
import { GeneratorAssignment } from './GeneratorAssignment.js';
import { WelfareVisitResult } from './WelfareVisitResult.js';
import { HeatingPointReport } from './HeatingPointReport.js';
import { AlertCampaign } from './AlertCampaign.js';

export type AppSchema = {
  NationalDecision: NationalDecision;
  GeneratorAssignment: GeneratorAssignment;
  WelfareVisitResult: WelfareVisitResult;
  HeatingPointReport: HeatingPointReport;
  AlertCampaign: AlertCampaign;
};

export const schema = [
  NationalDecision,
  GeneratorAssignment,
  WelfareVisitResult,
  HeatingPointReport,
  AlertCampaign,
];
