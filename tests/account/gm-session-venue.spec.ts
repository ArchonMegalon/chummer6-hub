import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from 'playwright/test';

const repoRoot = process.cwd();
const controllerPath = path.join(repoRoot, 'Chummer.Run.Api', 'Controllers', 'PublicLandingController.cs');
const venueControllerPath = path.join(repoRoot, 'Chummer.Run.Api', 'Controllers', 'GmSessionVenueController.cs');
const venueViewPath = path.join(repoRoot, 'Chummer.Run.Api', 'Views', 'PublicLanding', 'GmSessionVenue.cshtml');
const servicePath = path.join(repoRoot, 'Chummer.Run.Api', 'Services', 'Community', 'GmSessionVenueService.cs');
const adapterPath = path.join(repoRoot, 'Chummer.Run.Api', 'Services', 'Community', 'IGmSessionVenueAdapter.cs');

test('gm session venue routes keep private-by-default handoff and fail-closed create mode', async () => {
  const controller = readFileSync(controllerPath, 'utf8');
  const venueController = readFileSync(venueControllerPath, 'utf8');
  const view = readFileSync(venueViewPath, 'utf8');
  const service = readFileSync(servicePath, 'utf8');
  const adapter = readFileSync(adapterPath, 'utf8');

  expect(controller).toContain('[HttpGet("/community/runs/{runId}/venue")]');
  expect(controller).toContain('[HttpGet("/account/campaigns/{campaignId}/sessions/{sessionId}/venue")]');
  expect(controller).toContain('[HttpGet("/account/campaigns/{campaignId}/sessions/{sessionId}/venue/manage")]');
  expect(controller).toContain('[HttpGet("/account/campaigns/{campaignId}/sessions/{sessionId}/venue/closeout")]');

  expect(venueController).toContain('[HttpPost("manual-link")]');
  expect(venueController).toContain('[HttpPost("behuman")]');
  expect(venueController).toContain('[HttpPost("closeout")]');

  expect(view).toContain('Join live room');
  expect(view).toContain('Copy invite link');
  expect(view).toContain('Attendance sync remains consent-gated and optional.');
  expect(view).toContain('Create BeHuman room unavailable');
  expect(view).toContain('Provider create available');
  expect(view).toContain('No public room disclosure');

  expect(service).toContain('adapter_create_mode');
  expect(service).toContain('ConsentToShareAttendeeEmails');
  expect(adapter).toContain('Create BeHuman venue is unavailable until a verified adapter transport base URL exists.');
  expect(adapter).toContain('venue_url host is not an allowed BeHuman domain.');
  expect(adapter).toContain('venue_url may not include suspicious query payloads.');
});
