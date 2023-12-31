import adsk.core
import adsk.fusion
from dataclasses import dataclass
import io


tempBrepMgr = adsk.fusion.TemporaryBRepManager.get()


def dumpBody(body: adsk.fusion.BRepBody, indent = '  ') -> str:
	indent2 = indent * 2
	out = io.StringIO(
		f'{indent}name: {body.name}\n'
		f'{indent}isValid: {body.isValid}, isTemporary: {body.isTemporary}, isTransient: {body.isTransient}\n'
		f'{indent}bounds: '
		f'{body.boundingBox.minPoint.x} <= x <= {body.boundingBox.maxPoint.x}, '
		f'{body.boundingBox.minPoint.y} <= y <= {body.boundingBox.maxPoint.y}, '
		f'{body.boundingBox.minPoint.z} <= z <= {body.boundingBox.maxPoint.z}\n'
		f'{indent}isSolid: {body.isSolid}\n'
		f'{indent}volume: {(body.isSolid or None) and f"{body.volume} cm^3"}\n'
		f'{indent}parentComponent: {body.parentComponent}\n'
		f'{indent}baseFeature: {body.baseFeature}\n'
		f'{indent}lumps: {body.lumps.count}\n'
		f'{indent}shells: {body.shells.count}\n'
		f'{indent}faces: {body.faces.count}\n'
		f'{indent}edges: {body.edges.count}\n'
		f'{indent}vertices: {body.vertices.count}\n'
		f'{indent}wires: {body.wires.count}\n'
	)
	for i, lump in enumerate(body.lumps):
		for j, shell in enumerate(lump.shells):
			out.write(
				f'{indent}lumps[{i}].shells[{j}]:\n'
				f'{indent2}bounds: '
				f'{shell.boundingBox.minPoint.x} <= x <= {shell.boundingBox.maxPoint.x}, '
				f'{shell.boundingBox.minPoint.y} <= y <= {shell.boundingBox.maxPoint.y}, '
				f'{shell.boundingBox.minPoint.z} <= z <= {shell.boundingBox.maxPoint.z}\n'
				f'{indent2}isClosed: {shell.isClosed}\n'
				f'{indent2}isVoid: {shell.isVoid}\n'
				f'{indent2}area: {shell.area} cm^2\n'
				f'{indent2}volume: {shell.volume} cm^3\n'
				f'{indent2}faces: {shell.faces.count}\n'
				f'{indent2}edges: {shell.edges.count}\n'
				f'{indent2}vertices: {shell.vertices.count}\n'
			)
	for attribute in body.attributes or []:
		out.write(f'{indent}attribute: {attribute.groupName}/{attribute.name}: {attribute.value}\n')
	return out.getvalue()


def definitionOfBody(body: adsk.fusion.BRepBody) -> adsk.fusion.BRepBodyDefinition:
	"""
	Given a `body` create a `BRepBodyDefinition` for it.
	The body definition can be used to create a similar body with modifications.
	"""
	bodyDefinition = adsk.fusion.BRepBodyDefinition.create()
	bodyDefinition.doFullHealing = False
	for lump in body.lumps:
		lumpDefinition = bodyDefinition.lumpDefinitions.add()
		for shell in lump.shells:
			shellDefinition = lumpDefinition.shellDefinitions.add()
			for face in shell.faces:
				faceDefinition = shellDefinition.faceDefinitions.add(
					face.geometry, face.isParamReversed)
				for loop in face.loops:
					loopDefinition = faceDefinition.loopDefinitions.add()
					for coEdge in loop.coEdges:
						edge = coEdge.edge
						loopDefinition.bRepCoEdgeDefinitions.add(
							bodyDefinition.createEdgeDefinitionByCurve(
								bodyDefinition.createVertexDefinition(edge.startVertex.geometry),
								bodyDefinition.createVertexDefinition(edge.endVertex.geometry),
								edge.geometry),
							coEdge.isParamReversed)
			wire = shell.wire
			if wire:
				wireDefinition = shellDefinition.wireDefinition
				for coEdge in wire.coEdges:
					edge = coEdge.edge
					wireDefinition.wireEdgeDefinitions.add(
						bodyDefinition.createVertexDefinition(edge.startVertex.geometry),
						bodyDefinition.createVertexDefinition(edge.endVertex.geometry),
						edge.geometry)
	return bodyDefinition


def createSimpleBox(x, y, z, dx, dy, dz) -> adsk.fusion.BRepBody:
	"""
	Create a box in the current coordinate system given min point coordinates and dimensions.
	"""
	return tempBrepMgr.createBox(adsk.core.OrientedBoundingBox3D.create(
		adsk.core.Point3D.create(
			x + dx / 2,
			y + dy / 2,
			z + dz / 2),
		adsk.core.Vector3D.create(1, 0, 0),
		adsk.core.Vector3D.create(0, 1, 0),
		dx,
		dy,
		dz))


def createFaceFromCurves(curves: list[adsk.core.Curve3D]) -> adsk.fusion.BRepFace:
	"""
	Create a face (without holes) from the given closed planar `curves`.
	"""
	return tempBrepMgr.createFaceFromPlanarWires([
		tempBrepMgr.createWireFromCurves(curves)[0]]).faces[0]


def createPrism(base: adsk.fusion.BRepFace, height: float) -> adsk.fusion.BRepBody:
	"""
	Create a prism using the given `base` face and `height`.
	Use a negative `height` to reverse the direction of the prism.
	Any holes in the `base` face will be ignored and filled-in in the resulting solid prism.
	"""
	assert base.geometry.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType
	direction = base.geometry.normal
	direction.scaleBy(height)
	return createObliquePrism(base, direction)


def createObliquePrism(base: adsk.fusion.BRepFace, direction: adsk.core.Vector3D) -> adsk.fusion.BRepBody:
	"""
	Create an oblique prism using the given `base` face and sweep `direction`.
	Any holes in the `base` face will be ignored and filled-in in the resulting solid prism.
	"""
	assert base.geometry.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType

	translation = adsk.core.Matrix3D.create()
	translation.translation = direction

	# Create closed wires for both bases.
	baseWireA, _ = tempBrepMgr.createWireFromCurves(
		[e.geometry for e in base.loops[0].edges], False)
	baseWireB = tempBrepMgr.copy(baseWireA)
	tempBrepMgr.transform(baseWireB, translation)

	# Create both bases.
	baseFaceA = tempBrepMgr.createFaceFromPlanarWires([baseWireA])
	baseFaceB = tempBrepMgr.createFaceFromPlanarWires([baseWireB])

	# Create the side walls.
	sideFaces = tempBrepMgr.createRuledSurface(baseWireA.wires[0], baseWireB.wires[0])

	# Put all faces together.
	prism = sideFaces
	tempBrepMgr.booleanOperation(prism, baseFaceA, adsk.fusion.BooleanTypes.UnionBooleanType)
	tempBrepMgr.booleanOperation(prism, baseFaceB, adsk.fusion.BooleanTypes.UnionBooleanType)

	# Recreate the prism to make it a solid body.
	return definitionOfBody(prism).createBody()


def boundingBoxBody(body: adsk.fusion.BRepBody, margin = 0) -> adsk.fusion.BRepBody:
	"""
	Create a body that represents the bounding box of the given `body`.
	"""
	boundingBox = body.boundingBox
	minX, minY, minZ = boundingBox.minPoint.asArray()
	maxX, maxY, maxZ = boundingBox.maxPoint.asArray()
	return tempBrepMgr.createBox(adsk.core.OrientedBoundingBox3D.create(
		adsk.core.Point3D.create(
			(minX + maxX) / 2,
			(minY + maxY) / 2,
			(minZ + maxZ) / 2),
		adsk.core.Vector3D.create(1, 0, 0),
		adsk.core.Vector3D.create(0, 1, 0),
		maxX - minX + margin,
		maxY - minY + margin,
		maxZ - minZ + margin))


def aContainingBody(body: adsk.fusion.BRepBody) -> adsk.fusion.BRepBody:
	"""
	Create a body that is guaranteed to entirely contain the given `body`.

	TODO: Is a box or a sphere more efficient?
	"""
	boundingBox = body.boundingBox
	minPoint = boundingBox.minPoint
	diagonal = minPoint.vectorTo(boundingBox.maxPoint)
	diagonal.scaleBy(0.5)
	center = minPoint.copy()
	center.translateBy(diagonal)
	return tempBrepMgr.createSphere(center, diagonal.length + 1)

	# return boundingBoxBody(body, 1)


def anExternalBody(body: adsk.fusion.BRepBody) -> adsk.fusion.BRepBody:
	"""
	Create a body that is guaranteed NOT to intersect with the given solid `body`.

	TODO: Is a box or a sphere more efficient?
	"""
	outsidePoint = body.boundingBox.maxPoint.copy()
	outsidePoint.x = outsidePoint.x + 2
	return tempBrepMgr.createSphere(outsidePoint, 1)

	# outsidePoint = body.boundingBox.maxPoint.copy()
	# outsidePoint.x = outsidePoint.x + 2
	# return tempBrepMgr.createBox(adsk.core.OrientedBoundingBox3D.create(
	# 	outsidePoint,
	# 	adsk.core.Vector3D.create(1, 0, 0),
	# 	adsk.core.Vector3D.create(0, 1, 0),
	# 	1,
	# 	1,
	# 	1))


def anInternalBody(body: adsk.fusion.BRepBody) -> adsk.fusion.BRepBody:
	"""
	Create a body that is guaranteed to be entirely contained within the given solid `body`.
	"""
	tinySphere = tempBrepMgr.createSphere(body.faces[0].pointOnFace, 2**-16)
	tempBrepMgr.booleanOperation(tinySphere, body, adsk.fusion.BooleanTypes.IntersectionBooleanType)
	return tinySphere


@dataclass
class BooleanOperation:
	"""
	Represents a single boolean operation of a tool body acting on a target body to either:
		* cut the target body,
		* intersect with the target body, or
		* join with the target body
	"""
	targetBody: adsk.fusion.BRepBody
	toolBody: adsk.fusion.BRepBody
	operation: adsk.fusion.BooleanTypes

	@classmethod
	def difference(cls, targetBody: adsk.fusion.BRepBody, toolBody: adsk.fusion.BRepBody) -> 'BooleanOperation':
		return cls(
			targetBody=targetBody,
			toolBody=toolBody,
			operation=adsk.fusion.BooleanTypes.DifferenceBooleanType)

	@classmethod
	def intersection(cls, targetBody: adsk.fusion.BRepBody, toolBody: adsk.fusion.BRepBody) -> 'BooleanOperation':
		return cls(
			targetBody=targetBody,
			toolBody=toolBody,
			operation=adsk.fusion.BooleanTypes.IntersectBooleanType)

	@classmethod
	def union(cls, targetBody: adsk.fusion.BRepBody, toolBody: adsk.fusion.BRepBody) -> 'BooleanOperation':
		return cls(
			targetBody=targetBody,
			toolBody=toolBody,
			operation=adsk.fusion.BooleanTypes.UnionBooleanType)
