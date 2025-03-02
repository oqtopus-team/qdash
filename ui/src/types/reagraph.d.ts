declare module "reagraph" {
  export interface NodePositionArgs {
    nodes: Array<{
      id: string;
      data?: {
        position?: { x: number; y: number };
      };
    }>;
  }

  export interface GraphCanvasProps {
    nodes: any[];
    edges: any[];
    layoutType?: string;
    layoutOverrides?: {
      getNodePosition?: (
        id: string,
        args: NodePositionArgs
      ) => { x: number; y: number; z: number };
    };
    onNodePointerOver?: (node: any) => void;
    onEdgePointerOver?: (edge: any) => void;
    onNodeClick?: (node: any) => void;
    edgeArrowPosition?: string;
  }

  export const GraphCanvas: React.FC<GraphCanvasProps>;
}
