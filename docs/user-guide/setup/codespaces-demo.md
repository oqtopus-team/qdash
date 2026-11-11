# QDash Demo in Codespaces

The QDash Demo (sample data) runs a private QDash in a GitHub Codespace on the
[Fake backend](./fake-backend.md), with no local installation, lab hardware, or credentials
beyond your GitHub account. The codespace starts QDash with a virtual 64-qubit chip and starts a
calibration run in the background. Follow its progress in **Execution**; results appear in
**Task Results** and **Chip** as tasks finish. Use [Setup](../setup.md) instead for a deployment
that other people use.

## Decide Who Pays

GitHub bills a codespace's compute time and storage to the account that owns it. On the Free
plan, an organization cannot pay for codespaces, so the creator always pays.

For an organization that has a paid plan and wants each creator to pay, an organization owner
selects **User ownership** under **Settings → Codespaces → General → Codespace ownership**. With
this setting, a codespace created from the organization's repositories is always owned by and
billed to its creator's personal account. Organization members whose access to Codespaces is not
enabled can still create codespaces from public repositories, and they pay for those codespaces.
GitHub explains the options in
[Choosing who owns and pays for codespaces](https://docs.github.com/en/codespaces/managing-codespaces-for-your-organization/choosing-who-owns-and-pays-for-codespaces-in-your-organization).

Personal accounts include a monthly amount of compute and storage. Without a payment method,
GitHub blocks further use once that amount is used up. With paid usage enabled, a budget only
stops further usage if its spending enforcement is configured; an alert alone is not a cap. See
[About billing for GitHub Codespaces](https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-codespaces/about-billing-for-github-codespaces)
for the included amounts and prices. The demo requires a machine with at least 4 cores, which
uses the included compute twice as fast as the smallest, 2-core machine.

## Create the Codespace

1. In the repository README, select **Launch QDash Demo**. GitHub opens the codespace creation
   page with the branch and the **QDash Demo (sample data)** configuration selected.
2. Check that **Dev container configuration** shows **QDash Demo (sample data)**. The default
   configuration is the development container, which needs a local Docker host and does not
   start the demo.
3. Keep the 4-core machine type, or select a larger one, and select **Create codespace**.

Without the README button, select **Code → Codespaces** on the repository page, open the **...**
menu, select **New with options**, and choose the same configuration.

The first start builds the QDash images in the codespace, then starts, migrates, and seeds
QDash; on a 4-core machine it took about 11 minutes. Later starts reuse the images. The editor
opens after this startup finishes. The creation log ends with the sign-in details, and each time
the editor connects, a terminal shows them again:

```text
[qdash-demo] QDash:    https://<codespace-name>-5714.app.github.dev/login (in Codespaces: Ports tab, port 5714)
[qdash-demo] User:     admin
[qdash-demo] Password: <generated password>
```

The password is generated for this codespace and stored in its `.env`. To show the details in
another terminal, run:

```bash
bash .devcontainer/codespaces-demo/demo.sh credentials
```

## Open QDash

When the editor opens, the codespace asks the browser to open QDash in a new tab. Sign in with
the user and password from the terminal. If no tab opens, for example because the browser blocked
it, open the **Ports** tab and select the address of port **5714**, labelled **QDash Demo**.

Port 5714 is the only forwarded port. Codespaces keeps it private, so only your GitHub account can
open it. Do not change its visibility to public: anyone with the address could then reach the
sign-in page.

The virtual chip is **demo-64q**, and the saved workflow **demo_fake_calibration** runs the
**Fake Backend Calibration** template on MUX 0 to 3. Run the workflow again from **Workflow**, or
continue with [Run Your First Calibration](../first-calibration.md) to create another chip.
[What the Fake Backend Runs](./fake-backend.md#what-the-fake-backend-runs) lists the tasks and
targets. AI chat and figure analysis are not started in the demo.

## Stop, Restart, and Delete

Compute is billed while the codespace runs. Codespaces stops it after the idle timeout, 30 minutes
by default, which you can change under **Settings → Codespaces → Default idle timeout** in your
personal settings. Storage is billed for as long as the codespace exists, so delete it when you
finish the demo.

| Action | Effect | How |
| --- | --- | --- |
| Stop | Ends compute billing; keeps the data | On <https://github.com/codespaces>, open the **...** menu of the codespace and select **Stop codespace**, or run `gh codespace stop` |
| Restart | Starts QDash again with the same password, chip, and results | Open the codespace from <https://github.com/codespaces>; startup reruns the demo script |
| Delete | Ends all billing; removes the data | On <https://github.com/codespaces>, open the **...** menu and select **Delete**, or run `gh codespace delete` |

Once the chip has any execution, startup does not submit another run, including when the
previous run failed or was cancelled. Results you add are kept across restarts. To recover:

1. Open **Execution** and inspect the failed or cancelled run and its task errors.
2. Resolve the reported error; see [Operations](../operations.md#resolve-common-failures) if a
   service is unavailable.
3. Open **Workflow** and run **demo_fake_calibration** again. Follow the new run in **Execution**.

Startup waits up to 10 minutes for the services to come up before it adds the chip and run. If
a service fails to start, startup stops and prints that service's last log lines in place of
the sign-in details. If QDash does not answer after a restart, run the startup again in the
codespace terminal and read its output:

```bash
bash .devcontainer/codespaces-demo/demo.sh start
```

`demo.sh status` lists the services, and `demo.sh stop` stops QDash without stopping the
codespace. The databases are kept in Docker volumes inside the codespace, not in the checkout,
so `demo.sh stop` and restarts keep them; `docker compose down --volumes` deletes them.
