"use client";

import { useCallback, useRef } from "react";
import Image from "next/image";

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
        href="/"
        aria-current="page"
        aria-label="daisyUI"
        className="flex-0 btn btn-ghost gap-1 px-2 md:gap-2"
      >
        {/* Logo can be added here using Next.js Image component */}
      </a>
    </div>
  );
}

function ProfileModal({
  modalRef,
}: {
  modalRef: React.RefObject<HTMLDialogElement>;
}) {
  return (
    <dialog ref={modalRef} className="modal">
      <div className="modal-box w-96">
        <div className="card">
          <figure className="relative w-full h-64">
            <Image
              src="https://github.com/orangekame3.png"
              alt="Avatar"
              fill
              className="object-cover"
            />
          </figure>
          <div className="card-body py-2">
            <h2 className="card-title text-2xl">orangekame3</h2>
            <ul className="text-left">
              <li>Role: admin</li>
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

function Navbar() {
  const modalRef = useRef<HTMLDialogElement>(null);

  const openModal = useCallback(() => {
    modalRef.current?.showModal();
  }, []);

  return (
    <nav className="navbar w-full">
      <div className="flex flex-1 md:gap-1 lg:gap-2">
        <span className="tooltip tooltip-bottom before:text:text-xs before:content-[attr(data-tip)]">
          <label
            aria-label="Open menu"
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
          <div className="relative w-10 h-10 rounded-full shadow overflow-hidden">
            <Image
              alt="Avatar"
              src="https://github.com/orangekame3.png"
              fill
              className="object-cover"
            />
          </div>
        </div>
        <ul
          tabIndex={0}
          className="mt-3 z-[1] p-2 shadow menu menu-sm dropdown-content bg-base-100 rounded-box w-52"
        >
          <li>
            <button className="justify-between" onClick={openModal}>
              Profile
            </button>
          </li>
          <li>
            <button>Logout</button>
          </li>
        </ul>
      </div>
      <ProfileModal modalRef={modalRef} />
    </nav>
  );
}

export default Navbar;
