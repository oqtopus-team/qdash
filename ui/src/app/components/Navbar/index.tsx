"use client";

import { useCallback, useRef } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useAuth } from "@/app/contexts/AuthContext";
import { useAuthLogout } from "@/client/auth/auth";
import type { User } from "@/schemas";

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
  user,
}: {
  modalRef: React.RefObject<HTMLDialogElement>;
  user: User | null;
}) {
  return (
    <dialog ref={modalRef} className="modal">
      <div className="modal-box w-96">
        <div className="card">
          <figure className="relative w-full h-64">
            <div className="bg-gray-200 w-full h-full flex items-center justify-center">
              <span className="text-4xl">
                {user?.username?.[0]?.toUpperCase()}
              </span>
            </div>
          </figure>
          <div className="card-body py-2">
            <h2 className="card-title text-2xl">{user?.username}</h2>
            <ul className="text-left">
              <li>Email: {user?.email}</li>
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
  const router = useRouter();
  const { user, logout: authLogout } = useAuth();

  const openModal = useCallback(() => {
    modalRef.current?.showModal();
  }, []);

  const logoutMutation = useAuthLogout();
  const handleLogout = useCallback(async () => {
    try {
      await logoutMutation.mutateAsync();
      authLogout();
      router.push("/login");
    } catch (error) {
      console.error("Logout failed:", error);
    }
  }, [logoutMutation, authLogout, router]);

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
            <div className="bg-gray-200 w-full h-full flex items-center justify-center">
              <span className="text-2xl">
                {user?.username?.[0]?.toUpperCase()}
              </span>
            </div>
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
            <button onClick={handleLogout}>Logout</button>
          </li>
        </ul>
      </div>
      <ProfileModal modalRef={modalRef} user={user} />
    </nav>
  );
}

export default Navbar;
