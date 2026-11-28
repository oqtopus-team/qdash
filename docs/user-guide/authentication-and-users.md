# Authentication and Users

QDash uses system accounts and separate project roles.

## Sign In

Enter your username and password on the sign-in page. QDash opens **Execution** in your default
project. Sign out from the profile menu at the bottom of the sidebar.

![Signing in to QDash](/images/guides/login.gif)

## System Roles

| Role | Access |
| --- | --- |
| User | Own account and assigned projects |
| Admin | User creation, password resets, and administration |

Administrators still need membership to read a project's data; they can add themselves from
**Admin**. The initial administrator is configured during [Setup](./setup.md).

## Create Users

As an administrator, open **Admin**, create an account, and share its credentials securely.
Each new user receives a default project they own. Administrators also reset passwords here;
the user should change a reset password after signing in.

## Change a Password

Open **Settings → Account** and supply your current and new passwords. If you cannot sign in, ask an
administrator to reset your password.

## Change Your Avatar

Open **Settings → Account**, choose an avatar, and select **Save Profile**. To restore the
generated avatar, select **Use automatic avatar**, then **Save Profile**.

## API Authentication

Use **Settings → API Token** to configure a [client profile](../reference/clients/python.md#connect-to-a-deployment).
The profile holds the token and project. See [project roles](./projects-and-data-sharing.md#choose-a-project-role)
for the operations it can perform.
