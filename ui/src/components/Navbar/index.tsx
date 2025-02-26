function MenuIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="20"
      height="20"
      fill="none"
      viewBox="0 0 24 24"
      className="inline-block h-5 w-5 stroke-current md:h-6 md:w-6"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
        d="M4 6h16M4 12h16M4 18h16"
      ></path>
    </svg>
  );
}

function HiddenIcon() {
  return (
    <div className="flex items-center gap-2 lg:hidden">
      <a
        data-sveltekit-preload-data=""
        href="/"
        aria-current="page"
        aria-label="daisyUI"
        className="flex-0 btn btn-ghost gap-1 px-2 md:gap-2"
        data-svelte-h="svelte-dlyygu"
      >
        {/* <img src={Logo} className="w-3/5" /> */}
      </a>
    </div>
  );
}

function Navbar() {
  const openModal = () => {
    const modal = document.getElementById("profile_modal") as HTMLDialogElement;
    if (modal) modal.showModal();
  };
  return (
    <nav className="navbar w-full">
      <div className="flex flex-1 md:gap-1 lg:gap-2">
        <span className="tooltip tooltip-bottom before:text:text-xs before:content-[attr(data-tip)]">
          <label
            aria-label="Open menue"
            htmlFor="drawer"
            className="btn btn-square btn-ghost drawer-button lg:hidden"
          >
            <MenuIcon />
          </label>
        </span>
        <HiddenIcon />
      </div>
      <div className="dropdown dropdown-end">
        <div
          tabIndex={0}
          role="button"
          className="btn btn-ghost btn-circle avatar"
        >
          <div className="w-10 rounded-full shadow">
            <img alt="Avatar" src="https://github.com/orangekame3.png" />
          </div>
        </div>
        <ul
          tabIndex={0}
          className="mt-3 z-[1] p-2 shadow menu menu-sm dropdown-content bg-base-100 rounded-box w-52"
        >
          <li>
            <a className="justify-between" onClick={openModal}>
              Profile
            </a>
          </li>
          <li>
            <a>Logout</a>
          </li>
        </ul>
      </div>
      <ProfileModal />
    </nav>
  );
}

function ProfileModal() {
  return (
    <dialog id="profile_modal" className="modal">
      <div className="modal-box w-96">
        <div className="card">
          <figure>
            <img src="https://github.com/orangekame3.png" alt="Avatar" />
          </figure>
          <div className="card-body py-2">
            <h2 className="card-title text-2xl">orangekame3</h2>
            <ul className="text-left">
              <li>Role: admin</li>
              {/* Add more roles as needed */}
            </ul>
            <div className="modal-action">
              <form method="dialog">
                <button className="btn">Close</button>
              </form>
            </div>
          </div>
        </div>
      </div>
    </dialog>
  );
}

export default Navbar;
