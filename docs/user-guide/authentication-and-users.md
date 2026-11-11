# Authentication and Users

QDash combines system-wide user accounts with project-specific roles.

## Sign In

Open the QDash sign-in page and enter your username and password. After authentication, QDash
opens the Execution page in your default project.

![Signing in to QDash](/images/guides/login.gif)

Use the profile menu at the bottom of the sidebar to sign out. The same menu provides access to
personal settings and password changes.

## System Roles

| Role | Platform access |
| --- | --- |
| User | Sign in, update their own account, and access assigned projects. |
| Admin | Create users, reset passwords, and open the Admin page. |

The deployment creates its initial administrator during setup. See
[Setup](./setup.md#configure-shared-deployment-settings) for the required credentials. System
administrators do not automatically own every project; project membership still controls access
to project data. An administrator can add themselves to a project from **Admin** when they need
that access.

## Create Users

Only a system administrator can create an account. Open **Admin**, create the user, and provide
the credentials through an appropriate secret-sharing channel. QDash creates a default project
for the new account and makes that user its owner.

![Creating a user from the Admin page](/images/guides/create-user.gif)

Administrators can also reset a user's password from **Admin**. A reset replaces the current
password and should be followed by a user-initiated password change.

![Resetting a user's password from the Admin page](/images/guides/reset-password.gif)

## Change a Password

An authenticated user can change their own password from **Settings** by supplying the current
password and a new password. A user who cannot authenticate must ask an administrator for a
reset.

![Changing your password from Settings](/images/guides/change-password.gif)

## Change Your Avatar

Every user has an avatar. QDash generates it in the browser from your username, so the same
username gets the same automatic avatar on any QDash instance that runs the same QDash release.

To choose a different avatar:

1. Open **Settings** and select the **Account** tab.
2. Under **Avatar**, drag the avatar grid or focus it and use the arrow keys. The avatar in the
   center is selected and appears in the preview.
3. Optional: use **Shuffle**, **New shape**, **New colors**, or **New background** to vary the
   selection.
4. Select **Save Profile**. **Cancel** discards the selection.

To return to the generated avatar, select **Use automatic avatar**, then **Save Profile**. A chosen
avatar applies only to the QDash instance where you saved it. If QDash cannot load your chosen
avatar, for example during a network interruption, it shows your automatic avatar instead.

## API Authentication

Scripts authenticate with the token shown in **Settings → API Token**, saved in a client profile
with the project to use. The client then sends the token and project with every request, and the
token stays out of shell history; see
[Connect to a Deployment](../reference/clients/python.md#connect-to-a-deployment).

For a custom API integration, use the interactive OpenAPI page linked from QDash or the
[OpenAPI reference](../reference/openapi.md) for the current authentication and project-selection
contract.

System roles control account administration. Project roles separately control calibration data
and operations; see [Projects and Data Sharing](./projects-and-data-sharing.md#choose-a-project-role).
