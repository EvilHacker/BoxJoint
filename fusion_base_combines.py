import adsk.core
import adsk.fusion
from dataclasses import dataclass, field

from .fusion_util import *
from .fusion_brep_util import *


@dataclass
class _BooleanOperations:
	targetBody: adsk.fusion.BRepBody
	operations: list[BooleanOperation] = field(default_factory=list)


class BaseCombines:
	def __init__(self):
		self._opsByTargetBodyId: dict[str, _BooleanOperations] = {}

	def add(self, booleanOperation: BooleanOperation):
		self.addTargetBody(booleanOperation.targetBody).operations.append(booleanOperation)

	def addTargetBody(self, targetBody: adsk.fusion.BRepBody):
		return self._opsByTargetBodyId.setdefault(
			targetBody.revisionId, _BooleanOperations(targetBody))

	def createOrUpdate(self,
		existingFeatures: list[adsk.fusion.Feature],
		allowFeatureCreationAndDeletion
	) -> list[adsk.fusion.Feature]:
		orderedOpsByTargetBodyId: dict[str, _BooleanOperations] = {}
		existingFeaturesByTargetBodyId: dict[str, tuple[
			adsk.fusion.BaseFeature,  # base feature containing the tool body
			adsk.fusion.CombineFeature,  # join feature
			adsk.fusion.CombineFeature  # intersect feature
		]] = {}
		resultingFeatures = []  # existing plus any new features

		# Examine existing features in triples.
		for baseFeature, joinFeature, intersectFeature in zip(* [iter(existingFeatures)] * 3):
			targetBody = joinFeature.targetBody
			targetBodyId = targetBody.revisionId
			ops = self._opsByTargetBodyId.get(targetBodyId)
			if not ops and allowFeatureCreationAndDeletion:
				# Delete the features associated with the unknown target body.
				intersectFeature.deleteMe()
				joinFeature.deleteMe()
				baseFeature.deleteMe()
				adsk.core.Application.log("Deleting stuffs")
								
			else:
				# Add operations to this target body.
				adsk.core.Application.log("Add operations to this target body")
				orderedOpsByTargetBodyId[targetBodyId] = ops or _BooleanOperations(targetBody)

				# Add the existing features related this target body.
				existingFeaturesByTargetBodyId.setdefault(targetBodyId, (
					baseFeature, joinFeature, intersectFeature))

		if allowFeatureCreationAndDeletion:
			# Add operations to any target bodies that don't have existing features.
			for targetBodyId, ops in self._opsByTargetBodyId.items():
				orderedOpsByTargetBodyId[targetBodyId] = ops

		design: adsk.fusion.Design = adsk.core.Application.get().activeProduct
		component = design.activeComponent
		baseFeatures = component.features.baseFeatures
		combineFeatures = component.features.combineFeatures

		# Create or update the features for each target body.
		for targetBodyId, ops in orderedOpsByTargetBodyId.items():
			# Get existing features (if any).
			adsk.core.Application.log("Get existing features (if any)")
			baseFeature, joinFeature, intersectFeature = existingFeaturesByTargetBodyId.get(
				targetBodyId, (None, None, None))

			# Modify a copy of the original target body.
			
			# OG targetBody = ops.targetBody

			# Find targetBody in current model, not a stale reference
			bodies = {b.name: b for b in component.bRepBodies}
			targetBody = bodies.get(ops.targetBody.name)

			if not targetBody:
				print(f"[ERROR] Could not resolve target body: {ops.targetBody.name}")
				continue  # skip this one safely

			adsk.core.Application.log("targetBody")
			modifiedTargetBody = tempBrepMgr.copy(targetBody)
			for operation in ops.operations:
				tempBrepMgr.booleanOperation(
					modifiedTargetBody, operation.toolBody, operation.operation)

			# Create or update the BaseFeature.
			if baseFeature:
				# Update the existing BaseFeature.
				baseFeature.timelineObject.rollTo(rollBefore = False)
				baseFeature.startEdit()
				baseFeature.updateBody(baseFeature.bodies[0], modifiedTargetBody)
				baseFeature.finishEdit()
			else:
				# Create a new BaseFeature.
				initialDummyBody = aContainingBody(modifiedTargetBody)
				if resultingFeatures:
					resultingFeatures[-1].timelineObject.rollTo(rollBefore = False)
				baseFeature = baseFeatures.add()
				baseFeature.startEdit()
				component.bRepBodies.add(initialDummyBody, baseFeature)
				baseFeature.updateBody(baseFeature.bodies[0], modifiedTargetBody)
				baseFeature.finishEdit()
			baseFeature.sourceBodies[0].name = targetBody.name + ' *'
			resultingFeatures.append(baseFeature)

			# Create the CombineFeatures (if they don't exist yet).
			tools = newObjectCollection(baseFeature.bodies)
			for combineFeature, operation, isKeepToolBodies in [
				(joinFeature, adsk.fusion.FeatureOperations.JoinFeatureOperation, True),
				(intersectFeature, adsk.fusion.FeatureOperations.IntersectFeatureOperation, False),
			]:
				if combineFeature:
					# combineFeature.targetBody = targetBody
					if combineFeature.targetBody != targetBody:
						combineFeature.targetBody = targetBody
				else:
					# Create a new CombineFeature.
					resultingFeatures[-1].timelineObject.rollTo(rollBefore = False)
					combineInput = combineFeatures.createInput(targetBody, tools)
					combineInput.operation = operation
					combineInput.isKeepToolBodies = isKeepToolBodies
					combineFeature = combineFeatures.add(combineInput)
				resultingFeatures.append(combineFeature)

		return resultingFeatures
