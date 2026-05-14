import { test, expect } from 'playwright/test';

const baseUrl = 'https://chummer.run';
const routes = [
  '/',
  '/downloads',
  '/packages',
  '/ledger',
  '/feedback',
  '/status',
  '/mobile',
  '/karma-forge',
  '/help',
  '/contact',
  '/roadmap',
  '/changelog',
];

const genericLabels = new Set([
  'click here',
  'here',
  'learn more',
  'more',
  'open',
  'go',
]);

const checkedUrls = new Set<string>();

function extractAnchors(html: string) {
  const anchors: Array<{ href: string; rel: string; text: string; target: string }> = [];
  const regex = /<a\b([^>]*?)href="([^"]+)"([^>]*)>(.*?)<\/a>/gis;
  for (const match of html.matchAll(regex)) {
    const attrs = `${match[1]} ${match[3]}`;
    const rel = /rel="([^"]*)"/i.exec(attrs)?.[1] ?? '';
    const target = /target="([^"]*)"/i.exec(attrs)?.[1] ?? '';
    const text = match[4].replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
    anchors.push({ href: match[2], rel, text, target });
  }
  return anchors;
}

function extractForms(html: string) {
  return Array.from(html.matchAll(/<form\b[^>]*action="([^"]+)"/gi)).map((match) => match[1]);
}

async function auditPage(route: string) {
  const response = await fetch(`${baseUrl}${route}`);
  expect(response.status, `${route} should load`).toBeLessThan(400);
  const html = await response.text();

  const anchorData = extractAnchors(html);

  for (const anchor of anchorData) {
    expect(anchor.href, `${route} contains an anchor without href`).not.toBe('');

    const lowered = anchor.text.toLowerCase();
    expect(genericLabels.has(lowered), `${route} contains generic link label "${anchor.text}"`).toBeFalsy();
    expect(anchor.href.startsWith('javascript:'), `${route} contains javascript link`).toBeFalsy();
    expect(anchor.href.includes('/admin/'), `${route} leaked operator route ${anchor.href}`).toBeFalsy();
    expect(anchor.href.includes('/api/internal/'), `${route} leaked internal route ${anchor.href}`).toBeFalsy();

    if (anchor.href.startsWith('#')) {
      const id = anchor.href.slice(1);
      const targetPattern = new RegExp(`id="${id}"|name="${id}"`, 'i');
      expect(targetPattern.test(html), `${route} missing hash target ${anchor.href}`).toBeTruthy();
      continue;
    }

    const resolved = new URL(anchor.href, `${baseUrl}${route}`);
    if (resolved.protocol === 'mailto:' || resolved.protocol === 'tel:') {
      continue;
    }
    if (resolved.origin !== baseUrl) {
      expect(anchor.rel.includes('noopener') && anchor.rel.includes('noreferrer'),
        `${route} external link ${resolved.href} is missing rel`).toBeTruthy();
      continue;
    }

    const normalizedHref = resolved.href;
    if (checkedUrls.has(normalizedHref)) {
      continue;
    }
    checkedUrls.add(normalizedHref);

    const linkResponse = await fetch(normalizedHref, { redirect: 'follow' });
    expect(linkResponse.status, `${route} link ${resolved.pathname} is broken`).toBeLessThan(400);
  }

  const buttonData = Array.from(html.matchAll(/<button\b([^>]*)>(.*?)<\/button>/gis)).map((match) => {
    const attrs = match[1];
    const text = match[2].replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
    return {
      text,
      type: /type="([^"]*)"/i.exec(attrs)?.[1] ?? '',
      ariaControls: /aria-controls="([^"]*)"/i.exec(attrs)?.[1] ?? '',
      name: /name="([^"]*)"/i.exec(attrs)?.[1] ?? '',
    };
  });

  for (const button of buttonData) {
    const lowered = button.text.toLowerCase();
    expect(button.text.length > 0 || button.ariaControls.length > 0,
      `${route} has an unlabeled visible button`).toBeTruthy();
    expect(genericLabels.has(lowered), `${route} contains generic button label "${button.text}"`).toBeFalsy();
  }

  const formActions = extractForms(html);

  for (const action of formActions) {
    expect(action, `${route} contains a form without action`).not.toBe('');
  }
}

test('all visible public links and actions stay usable', async () => {
  test.setTimeout(120000);
  for (const route of routes) {
    await auditPage(route);
  }
});
