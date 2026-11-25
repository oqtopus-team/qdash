#!/usr/bin/env node
// The `qdash` executable of @oqtopus-team/qdash-sdk; see config-init.ts.
import { runCli } from "./config-init.js";

process.exitCode = runCli(process.argv.slice(2));
