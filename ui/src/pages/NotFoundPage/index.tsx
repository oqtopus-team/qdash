import { Link } from "react-router-dom";

export const NotFoundPage = () => {
  return (
    <div className="w-full px-4" style={{ width: "calc(100vw - 20rem)" }}>
      <div
        className="hero h-screen"
        style={{ backgroundImage: "url(src/assets/404.png)" }}
      >
        <div className="hero-overlay bg-opacity-60"></div>
        <div className="hero-content text-center text-neutral-content">
          <div className="max-w-md">
            <h1 className="mb-5 text-5xl font-bold">404 NOT FOUND</h1>
            <p className="mb-5">お探しのページが見つかりませんでした。</p>
            <button className="btn btn-primary">
              <Link to="/dashboard">Topに戻る</Link>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
