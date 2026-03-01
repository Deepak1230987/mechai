/**
 * ThreeDViewer — enhanced 3D viewer with operation highlighting,
 * setup orientation, tool axis visualization, and bounding boxes.
 */

import { useEffect, useRef, useCallback, useState } from "react";
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
const HIGHLIGHT_COLOR = 0x2563eb;
const DIM_OPACITY = 0.15;
const TOOL_AXIS_COLOR = 0x14b8a6;
const BBOX_COLOR = 0xf59e0b;

export function ThreeDViewer() {
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const modelRef = useRef<THREE.Group | null>(null);
  const highlightGroupRef = useRef<THREE.Group>(new THREE.Group());
  const animFrameRef = useRef<number>(0);

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [currentSetup, setCurrentSetup] = useState(0);

  const { gltfUrl, selectedOperationId, spatialMap, plan } =
    useWorkspaceStore();

  const setupCount = plan?.setups?.length ?? 1;

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

    // Bounding box wireframe
    const bb = spatialOp.bounding_box;
    const size = new THREE.Vector3(
      Math.max(bb.x_max - bb.x_min, 0.2),
      Math.max(bb.y_max - bb.y_min, 0.2),
      Math.max(bb.z_max - bb.z_min, 0.2),
    );
    const bbGeo = new THREE.BoxGeometry(size.x, size.y, size.z);
    const bbMat = new THREE.MeshBasicMaterial({
      color: BBOX_COLOR,
      wireframe: true,
      transparent: true,
      opacity: 0.6,
    });
    const bbMesh = new THREE.Mesh(bbGeo, bbMat);
    bbMesh.position.set(
      spatialOp.centroid.x,
      spatialOp.centroid.y,
      spatialOp.centroid.z,
    );
    hGroup.add(bbMesh);

    // Highlight sphere at centroid
    const sphereGeo = new THREE.SphereGeometry(0.08, 16, 16);
    const sphereMat = new THREE.MeshBasicMaterial({
      color: HIGHLIGHT_COLOR,
      transparent: true,
      opacity: 0.8,
    });
    const sphere = new THREE.Mesh(sphereGeo, sphereMat);
    sphere.position.copy(bbMesh.position);
    hGroup.add(sphere);

    // Tool axis line
    const axisMap: Record<string, THREE.Vector3> = {
      "Z-": new THREE.Vector3(0, 0, -1),
      "Z+": new THREE.Vector3(0, 0, 1),
      "Y-": new THREE.Vector3(0, -1, 0),
      "Y+": new THREE.Vector3(0, 1, 0),
      "X-": new THREE.Vector3(-1, 0, 0),
      "X+": new THREE.Vector3(1, 0, 0),
    };
    const axisDir = axisMap[spatialOp.tool_axis] ?? new THREE.Vector3(0, 0, -1);

    const origin = new THREE.Vector3(
      spatialOp.centroid.x,
      spatialOp.centroid.y,
      spatialOp.centroid.z,
    );
    const arrowHelper = new THREE.ArrowHelper(
      axisDir,
      origin,
      1.0,
      TOOL_AXIS_COLOR,
      0.15,
      0.08,
    );
    hGroup.add(arrowHelper);
  }, [selectedOperationId, spatialMap]);

  // ── Setup rotation ───────────────────────────────────────────────────
  const handleSetupFlip = useCallback(() => {
    const next = (currentSetup + 1) % setupCount;
    setCurrentSetup(next);

    if (modelRef.current) {
      const orientations = ["TOP", "BOTTOM", "FRONT", "BACK", "LEFT", "RIGHT"];
      const setupOrientation =
        plan?.setups?.[next]?.orientation ??
        orientations[next % orientations.length];

      const rotationMap: Record<string, [number, number, number]> = {
        TOP: [0, 0, 0],
        BOTTOM: [Math.PI, 0, 0],
        FRONT: [-Math.PI / 2, 0, 0],
        BACK: [Math.PI / 2, 0, 0],
        LEFT: [0, 0, Math.PI / 2],
        RIGHT: [0, 0, -Math.PI / 2],
      };

      const [rx, ry, rz] = rotationMap[setupOrientation] ?? [0, 0, 0];

      // Smooth rotation animation
      const startRx = modelRef.current.rotation.x;
      const startRy = modelRef.current.rotation.y;
      const startRz = modelRef.current.rotation.z;
      const duration = 600;
      const startTime = performance.now();

      const animateRotation = (now: number) => {
        const t = Math.min((now - startTime) / duration, 1);
        const ease = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
        modelRef.current!.rotation.x = startRx + (rx - startRx) * ease;
        modelRef.current!.rotation.y = startRy + (ry - startRy) * ease;
        modelRef.current!.rotation.z = startRz + (rz - startRz) * ease;
        if (t < 1) requestAnimationFrame(animateRotation);
      };
      requestAnimationFrame(animateRotation);
    }
  }, [currentSetup, setupCount, plan?.setups]);

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />

      {/* Setup badge + flip button */}
      <div className="absolute top-3 left-3 flex items-center gap-2">
        <Badge variant="secondary" className="text-[11px] font-mono">
          Setup {currentSetup + 1}/{setupCount}
        </Badge>
        {setupCount > 1 && (
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 bg-background/60 backdrop-blur-sm hover:bg-background/80"
            onClick={handleSetupFlip}
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>

      {/* Selected operation info */}
      {selectedOperationId && spatialMap && (
        <div className="absolute bottom-3 left-3 rounded-md bg-background/80 backdrop-blur-sm border border-border px-3 py-2">
          <p className="text-[11px] text-muted-foreground">
            Selected Operation
          </p>
          <p className="text-xs font-mono text-foreground">
            {spatialMap.spatial_operations.find(
              (op) => op.operation_id === selectedOperationId,
            )?.operation_type ?? selectedOperationId.slice(0, 12)}
          </p>
        </div>
      )}

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
