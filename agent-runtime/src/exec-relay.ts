/**
 * The daemon command of the runtime's pi-env `Connection`: relays the
 * daemon's stdin and stdout to the agent-exec server over a Unix socket.
 *
 * Started as `bun exec-relay.ts --socket PATH --owner ID serve --token HEX`;
 * the last three arguments are what pi-env appends. The first line sent is the
 * hello the server expects (exec/protocol.ts); everything after it is the
 * daemon's own protocol, which this relay never interprets.
 */
import { connect } from "node:net";

function option(args: string[], name: string): string | undefined {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : undefined;
}

const args = process.argv.slice(2);
const path = option(args, "--socket");
const owner = option(args, "--owner");
const serve = args.indexOf("serve");
const argv = serve >= 0 ? args.slice(serve) : [];

if (!path || !owner || argv.length === 0) {
  console.error("exec-relay: expected --socket, --owner, and the daemon arguments");
  process.exit(2);
}

const socket = connect({ path }, () => {
  socket.write(`${JSON.stringify({ owner, argv })}\n`);
  process.stdin.pipe(socket);
  socket.pipe(process.stdout);
});
socket.on("error", (error) => {
  console.error(`exec-relay: ${error.message}`);
  process.exit(1);
});
// Let what the daemon last wrote reach stdout before the process ends.
socket.on("close", () => process.stdout.write("", () => process.exit(0)));
process.stdin.on("end", () => socket.end());
