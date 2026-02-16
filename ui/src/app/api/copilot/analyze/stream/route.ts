import { proxySSEStream } from "../../proxy-stream";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  return proxySSEStream(request, "/copilot/analyze/stream");
}
