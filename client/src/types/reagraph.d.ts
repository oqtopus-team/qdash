declare module "reagraph" {
  export interface NodePositionArgs {
    nodes: {
      id: string;
      data: {
        position?: {
          x: number;
          y: number;
        };
      };
    }[];
  }

  export interface InternalGraphPosition {
    id: string;
    x: number;
    y: number;
    z: number;
    vx: number;
    vy: number;
    fx: number | null;
    fy: number | null;
    data: any;
    links: any[];
    index: number;
  }

  export interface GraphCanvasProps {
    edgeArrowPosition?: "none" | "start" | "end" | "both";
    layoutType?: "custom" | "force" | "tree";
    layoutOverrides?: {
      getNodePosition: (id: string, args: NodePositionArgs) => InternalGraphPosition;
    };
    nodes: any[];
    edges: any[];
    onNodePointerOver?: (node: any) => void;
    onEdgePointerOver?: (edge: any) => void;
  }

  export const GraphCanvas: React.FC<GraphCanvasProps>;
  export function createColumnHelper<T>(): any;
}
