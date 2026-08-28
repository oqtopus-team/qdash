# Authentication and Users

QDash combines system-wide user accounts with project-specific roles.

## Sign In

Open `/login` and enter your username and password. After authentication, QDash opens the
Execution page in your default project.

![Signing in to QDash](/images/guides/login.gif)

Use the profile menu at the bottom of the sidebar to sign out. The same menu provides access to
personal settings and password changes.

## System Roles

| Role | Platform access |
| --- | --- |
| User | Sign in, update the own account, and access assigned projects. |
| Admin | Create users, reset passwords, and open the Admin page. |

The initial administrator is configured with `QDASH_ADMIN_USERNAME`. System administrators do
not automatically own every project; project membership still controls access to project data.

## Create Users

Only a system administrator can create an account. Open **Admin**, create the user, and provide
the credentials through an appropriate secret-sharing channel. QDash creates a default project
for the new account and makes that user its owner.

Administrators can also reset a user's password from **Admin**. A reset replaces the current
password and should be followed by a user-initiated password change.

## Change a Password

An authenticated user can change their own password from **Settings** by supplying the current
password and a new password. A user who cannot authenticate must ask an administrator for a
reset.

## API Authentication

Automation should use a saved [QDash Client](./qdash-client.md) profile or its documented
`QDASH_*` environment variables. The client handles authentication and project headers without
placing tokens directly in shell history.

Raw API consumers authenticate through `/auth/login`, send the returned bearer token in the
`Authorization` header, and select project-scoped data with `X-Project-Id`. Use the interactive
OpenAPI page linked from QDash or the [OpenAPI reference](../reference/openapi.md) for current
request and response schemas.

## Authorization Layers

System and project roles answer different questions:

- The system role controls account administration.
- The project role controls access to a project's calibration data and operations.

See [Projects and Data Sharing](./projects-and-sharing.md) for owner, editor, and viewer
permissions.
