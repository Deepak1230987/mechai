/**
 * ThreeDViewer — enhanced 3D viewer with operation highlighting,
 * setup orientation, tool axis visualization, and bounding boxes.
 *
 * Coordinate transformation:
 *   The glTF model is normalized to fit within a ~2-unit cube centered at origin.
 *   Spatial coordinates from the backend are in model-space (mm).
 *   We store the normalization transform (scale + offset) and apply it
 *   to spatial data so highlights align perfectly with the mesh.
 */

import { useEffect, useRef, useCallback, useState, useMemo } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { useWorkspaceStore } from "@/store/workspaceStore";
import { Box, Loader2, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const BG_COLOR = 0x0f172a;
const GRID_COLOR1 = 0x334155;
const GRID_COLOR2 = 0x1e293b;
const HIGHLIGHT_FILL_COLOR = 0x2563eb;
const HIGHLIGHT_WIRE_COLOR = 0x60a5fa;
const DIM_OPACITY = 0.18;
const TOOL_AXIS_COLOR = 0x14b8a6;
const BBOX_COLOR = 0xf59e0b;
const CENTROID_COLOR = 0xef4444;

/** Stored normalization: viewer_coord = (model_mm * scale) + offset */
interface ModelTransform {
  scale: number;
  offset: THREE.Vector3;
}

export function ThreeDViewer() {
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const modelRef = useRef<THREE.Group | null>(null);
  const highlightGroupRef = useRef<THREE.Group>(new THREE.Group());
  const animFrameRef = useRef<number>(0);
  const transformRef = useRef<ModelTransform | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const {
    gltfUrl,
    selectedOperationId,
    spatialMap,
    plan,
    selectedSetupIndex,
    selectSetup,
  } = useWorkspaceStore();

  const setupCount = plan?.setups?.length ?? 1;

  // Current setup orientation from plan
  const currentSetupOrientation = useMemo(() => {
    if (!plan?.setups?.[selectedSetupIndex]) return "TOP";
    return plan.setups[selectedSetupIndex].orientation ?? "TOP";
  }, [plan?.setups, selectedSetupIndex]);

  // ── Coordinate transform helper ──────────────────────────────────────
  // Maps from model-space mm coords to viewer-space coords.
  // CAD typically uses Z-up; Three.js uses Y-up, so we swap Y↔Z.
  const toViewerCoord = useCallback(
    (modelX: number, modelY: number, modelZ: number): THREE.Vector3 => {
      const t = transformRef.current;
      if (!t) return new THREE.Vector3(0, 0, 0);
      return new THREE.Vector3(
        modelX * t.scale + t.offset.x,
        modelZ * t.scale + t.offset.y,
        modelY * t.scale + t.offset.z,
      );
    },
    [],
  );

  const toViewerSize = useCallback(
    (sizeX: number, sizeY: number, sizeZ: number): THREE.Vector3 => {
      const t = transformRef.current;
      if (!t) return new THREE.Vector3(0.2, 0.2, 0.2);
      return new THREE.Vector3(
        Math.max(Math.abs(sizeX * t.scale), 0.02),
        Math.max(Math.abs(sizeZ * t.scale), 0.02),
        Math.max(Math.abs(sizeY * t.scale), 0.02),
      );
    },
    [],
  );

  // ── Scene setup ──────────────────────────────────────────────────────
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(BG_COLOR);
    sceneRef.current = scene;

    const width = container.clientWidth;
    const height = container.clientHeight || 500;
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.set(3, 3, 3);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Lighting
    scene.add(new THREE.AmbientLight(0xffffff, 0.5));
    const dl1 = new THREE.DirectionalLight(0xffffff, 0.9);
    dl1.position.set(5, 10, 7.5);
    scene.add(dl1);
    const dl2 = new THREE.DirectionalLight(0xffffff, 0.3);
    dl2.position.set(-5, 5, -5);
    scene.add(dl2);

    // Grid
    scene.add(new THREE.GridHelper(10, 20, GRID_COLOR1, GRID_COLOR2));

    // Highlight group
    scene.add(highlightGroupRef.current);

    // Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.1;
    controls.minDistance = 0.5;
    controls.maxDistance = 50;
    controlsRef.current = controls;

    // Animation loop
    function animate() {
      animFrameRef.current = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    }
    animate();

    // Resize
    const handleResize = () => {
      const w = container.clientWidth;
      const h = container.clientHeight || 500;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      cancelAnimationFrame(animFrameRef.current);
      controls.dispose();
      renderer.dispose();
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh) {
          obj.geometry?.dispose();
          if (Array.isArray(obj.material)) {
            obj.material.forEach((m: THREE.Material) => m.dispose());
          } else {
            (obj.material as THREE.Material)?.dispose();
          }
        }
      });
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, []);

  // ── Load glTF model ──────────────────────────────────────────────────
  useEffect(() => {
    if (
      !gltfUrl ||
      !sceneRef.current ||
      !cameraRef.current ||
      !controlsRef.current
    ) {
      if (!gltfUrl) setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError("");

    const loader = new GLTFLoader();
    loader.load(
      gltfUrl,
      (gltf) => {
        // Remove previous model
        if (modelRef.current && sceneRef.current) {
          sceneRef.current.remove(modelRef.current);
        }

        const model = gltf.scene;
        const box = new THREE.Box3().setFromObject(model);
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);
        const scale = 2 / maxDim;
        model.scale.setScalar(scale);
        model.position.sub(center.multiplyScalar(scale));

        // Store the normalization transform for spatial coordinate mapping
        transformRef.current = {
          scale,
          offset: model.position.clone(),
        };

        sceneRef.current!.add(model);
        modelRef.current = model;

        cameraRef.current!.position.set(2, 2, 2);
        controlsRef.current!.target.set(0, 0, 0);
        controlsRef.current!.update();

        setIsLoading(false);
      },
      undefined,
      () => {
        setError("Failed to load 3D model");
        setIsLoading(false);
      },
    );
  }, [gltfUrl]);

  // ── Highlight selected operation ─────────────────────────────────────
  useEffect(() => {
    const hGroup = highlightGroupRef.current;
    // Clear previous highlights
    while (hGroup.children.length > 0) {
      const child = hGroup.children[0];
      if (child instanceof THREE.Mesh) {
        child.geometry?.dispose();
        (child.material as THREE.Material)?.dispose();
      }
      hGroup.remove(child);
    }

    // Dim/undim model
    if (modelRef.current) {
      modelRef.current.traverse((obj) => {
        if (obj instanceof THREE.Mesh && obj.material) {
          const mat = obj.material as THREE.MeshStandardMaterial;
          mat.transparent = !!selectedOperationId;
          mat.opacity = selectedOperationId ? DIM_OPACITY : 1;
        }
      });
    }

    if (!selectedOperationId || !spatialMap) return;

    const spatialOp = spatialMap.spatial_operations.find(
      (op) => op.operation_id === selectedOperationId,
    );
    if (!spatialOp) return;

    const bb = spatialOp.bounding_box;
    const sizeX = Math.max(bb.x_max - bb.x_min, 0.5);
    const sizeY = Math.max(bb.y_max - bb.y_min, 0.5);
    const sizeZ = Math.max(bb.z_max - bb.z_min, 0.5);
    const centerX = (bb.x_min + bb.x_max) / 2;
    const centerY = (bb.y_min + bb.y_max) / 2;
    const centerZ = (bb.z_min + bb.z_max) / 2;

    // Convert to viewer coordinates
    const viewerCenter = toViewerCoord(centerX, centerY, centerZ);
    const viewerSize = toViewerSize(sizeX, sizeY, sizeZ);

    // Semi-transparent filled bounding box
    const fillGeo = new THREE.BoxGeometry(
      viewerSize.x,
      viewerSize.y,
      viewerSize.z,
    );
    const fillMat = new THREE.MeshBasicMaterial({
      color: HIGHLIGHT_FILL_COLOR,
      transparent: true,
      opacity: 0.15,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    const fillMesh = new THREE.Mesh(fillGeo, fillMat);
    fillMesh.position.copy(viewerCenter);
    hGroup.add(fillMesh);

    // Wireframe overlay
    const wireGeo = new THREE.BoxGeometry(
      viewerSize.x,
      viewerSize.y,
      viewerSize.z,
    );
    const wireMat = new THREE.MeshBasicMaterial({
      color: HIGHLIGHT_WIRE_COLOR,
      wireframe: true,
      transparent: true,
      opacity: 0.5,
    });
    const wireMesh = new THREE.Mesh(wireGeo, wireMat);
    wireMesh.position.copy(viewerCenter);
    hGroup.add(wireMesh);

    // Bright edge lines
    const edgesGeo = new THREE.EdgesGeometry(fillGeo);
    const edgesMat = new THREE.LineBasicMaterial({
      color: BBOX_COLOR,
      transparent: true,
      opacity: 0.9,
    });
    const edgesLine = new THREE.LineSegments(edgesGeo, edgesMat);
    edgesLine.position.copy(viewerCenter);
    hGroup.add(edgesLine);

    // Centroid indicator sphere
    const centroid = spatialOp.centroid;
    const viewerCentroid = toViewerCoord(centroid.x, centroid.y, centroid.z);
    const sphereGeo = new THREE.SphereGeometry(0.04, 16, 16);
    const sphereMat = new THREE.MeshBasicMaterial({
      color: CENTROID_COLOR,
      transparent: true,
      opacity: 0.9,
    });
    const sphere = new THREE.Mesh(sphereGeo, sphereMat);
    sphere.position.copy(viewerCentroid);
    hGroup.add(sphere);

    // Tool axis arrow
    const axisMap: Record<string, THREE.Vector3> = {
      "Z-": new THREE.Vector3(0, -1, 0),
      "Z+": new THREE.Vector3(0, 1, 0),
      "Y-": new THREE.Vector3(0, 0, -1),
      "Y+": new THREE.Vector3(0, 0, 1),
      "X-": new THREE.Vector3(-1, 0, 0),
      "X+": new THREE.Vector3(1, 0, 0),
    };
    const axisDir = axisMap[spatialOp.tool_axis] ?? new THREE.Vector3(0, -1, 0);

    const arrowOrigin = viewerCentroid
      .clone()
      .addScaledVector(axisDir.clone().negate(), 0.5);
    const arrowHelper = new THREE.ArrowHelper(
      axisDir,
      arrowOrigin,
      0.4,
      TOOL_AXIS_COLOR,
      0.08,
      0.05,
    );
    hGroup.add(arrowHelper);

    // Dashed approach line
    const dashMat = new THREE.LineDashedMaterial({
      color: TOOL_AXIS_COLOR,
      dashSize: 0.03,
      gapSize: 0.02,
      transparent: true,
      opacity: 0.4,
    });
    const lineGeo = new THREE.BufferGeometry().setFromPoints([
      arrowOrigin.clone().addScaledVector(axisDir.clone().negate(), 0.25),
      arrowOrigin,
    ]);
    const dashLine = new THREE.Line(lineGeo, dashMat);
    dashLine.computeLineDistances();
    hGroup.add(dashLine);
  }, [selectedOperationId, spatialMap, toViewerCoord, toViewerSize]);

  // ── Setup rotation (smooth animation) ────────────────────────────────
  useEffect(() => {
    if (!modelRef.current) return;

    const rotationMap: Record<string, [number, number, number]> = {
      TOP: [0, 0, 0],
      BOTTOM: [Math.PI, 0, 0],
      FRONT: [-Math.PI / 2, 0, 0],
      BACK: [Math.PI / 2, 0, 0],
      LEFT: [0, 0, Math.PI / 2],
      RIGHT: [0, 0, -Math.PI / 2],
    };

    const [rx, ry, rz] = rotationMap[currentSetupOrientation] ?? [0, 0, 0];

    const startRx = modelRef.current.rotation.x;
    const startRy = modelRef.current.rotation.y;
    const startRz = modelRef.current.rotation.z;

    if (
      Math.abs(startRx - rx) < 0.01 &&
      Math.abs(startRy - ry) < 0.01 &&
      Math.abs(startRz - rz) < 0.01
    ) {
      return;
    }

    const duration = 600;
    const startTime = performance.now();
    const model = modelRef.current;

    const animateRotation = (now: number) => {
      const t = Math.min((now - startTime) / duration, 1);
      const ease = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      model.rotation.x = startRx + (rx - startRx) * ease;
      model.rotation.y = startRy + (ry - startRy) * ease;
      model.rotation.z = startRz + (rz - startRz) * ease;
      if (t < 1) requestAnimationFrame(animateRotation);
    };
    requestAnimationFrame(animateRotation);
  }, [currentSetupOrientation]);

  // ── Setup flip handler ───────────────────────────────────────────────
  const handleSetupFlip = useCallback(() => {
    const next = (selectedSetupIndex + 1) % setupCount;
    selectSetup(next);
  }, [selectedSetupIndex, setupCount, selectSetup]);

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />

      {/* Setup badge + flip button */}
      <div className="absolute top-3 left-3 flex items-center gap-2">
        <Badge variant="secondary" className="text-[11px] font-mono">
          Setup {selectedSetupIndex + 1}/{setupCount}
          {currentSetupOrientation !== "TOP" && ` · ${currentSetupOrientation}`}
        </Badge>
        {setupCount > 1 && (
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 bg-background/60 backdrop-blur-sm hover:bg-background/80"
            onClick={handleSetupFlip}
            title="Flip to next setup orientation"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>

      {/* Selected operation info */}
      {selectedOperationId &&
        spatialMap &&
        (() => {
          const spatialOp = spatialMap.spatial_operations.find(
            (op) => op.operation_id === selectedOperationId,
          );
          return spatialOp ? (
            <div className="absolute bottom-3 left-3 rounded-md bg-background/80 backdrop-blur-sm border border-border px-3 py-2 max-w-[280px]">
              <p className="text-[11px] text-muted-foreground mb-0.5">
                Selected Operation
              </p>
              <p className="text-xs font-semibold text-foreground">
                {spatialOp.operation_type}
              </p>
              <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px] text-muted-foreground">
                <span>
                  Feature:{" "}
                  <span className="font-mono text-foreground">
                    {spatialOp.feature_id.slice(0, 16)}
                  </span>
                </span>
                <span>
                  Tool:{" "}
                  <span className="font-mono text-foreground">
                    {spatialOp.tool_axis}
                  </span>
                </span>
                <span>
                  Depth:{" "}
                  <span className="font-mono text-foreground">
                    {spatialOp.depth.toFixed(1)}mm
                  </span>
                </span>
                <span>
                  Time:{" "}
                  <span className="font-mono text-foreground">
                    {spatialOp.estimated_time.toFixed(1)}s
                  </span>
                </span>
              </div>
            </div>
          ) : null;
        })()}

      {/* Loading overlay */}
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-background/80">
          <div className="flex flex-col items-center gap-2">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-sm text-muted-foreground">Loading 3D model…</p>
          </div>
        </div>
      )}

      {/* No model placeholder */}
      {!gltfUrl && !isLoading && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center">
            <Box className="mx-auto mb-2 h-12 w-12 text-muted-foreground/30" />
            <p className="text-sm text-muted-foreground">
              No 3D model available
            </p>
            <p className="text-xs text-muted-foreground/60 mt-1">
              Upload a STEP/IGES file for 3D viewing
            </p>
          </div>
        </div>
      )}

      {/* Error overlay */}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center bg-background/80">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}
    </div>
  );
}
