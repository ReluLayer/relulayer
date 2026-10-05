import type { APIRoute } from 'astro';

interface LeadPayload {
  name?: string;
  email?: string;
  organization?: string;
  role?: string;
  interestArea?: string;
  message?: string;
}

const requiredFields: (keyof LeadPayload)[] = ['name', 'email', 'organization', 'role', 'interestArea'];

export const POST: APIRoute = async ({ request }) => {
  try {
    const contentType = request.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      return new Response(
        JSON.stringify({ success: false, error: 'Content-Type must be application/json.' }),
        { status: 415, headers: { 'Content-Type': 'application/json' } }
      );
    }

    const payload: LeadPayload = await request.json();

    const missing = requiredFields.filter((field) => !payload[field]?.trim());
    if (missing.length > 0) {
      return new Response(
        JSON.stringify({ success: false, error: `Missing required fields: ${missing.join(', ')}.` }),
        { status: 400, headers: { 'Content-Type': 'application/json' } }
      );
    }

    const email = payload.email?.trim() || '';
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return new Response(
        JSON.stringify({ success: false, error: 'Invalid email address.' }),
        { status: 400, headers: { 'Content-Type': 'application/json' } }
      );
    }

    const leadRecord = {
      ...payload,
      submittedAt: new Date().toISOString(),
      source: 'sbir-gtm-website',
      uei: 'G9WFN3AL69J3',
      cage: '20JX8',
    };

    console.log('[Lead Captured]', JSON.stringify(leadRecord, null, 2));

    return new Response(
      JSON.stringify({
        success: true,
        message: 'Lead captured successfully. Capability statement download initiated.',
        leadId: `ALG-${Date.now()}`,
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown server error';
    return new Response(
      JSON.stringify({ success: false, error: message }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    );
  }
};

export const GET: APIRoute = () => {
  return new Response(
    JSON.stringify({ success: false, error: 'This endpoint accepts POST requests only.' }),
    { status: 405, headers: { 'Content-Type': 'application/json', Allow: 'POST' } }
  );
};
