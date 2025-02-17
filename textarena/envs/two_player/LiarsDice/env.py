import random
import re
from typing import Any, Dict, Optional, Tuple, List

import textarena as ta


class LiarsDiceEnv(ta.Env):
    """
    Environment for the Liar's Dice Game.
    """

    def __init__(
        self,
        num_dice: Optional[int] = 5,
    ):
        """
        Initialize the Liar's Dice game environment.

        Args:
            num_dice (int): Number of dice each player rolls.
        """
        self.environment_name = "Liar's Dice"
        self.num_dice = num_dice

        # Initialize game state variables
        self.state = ta.State(
            num_players=2,
            max_turns=None,  # Game ends when a bluff is called
            render_keys=[
                ["dice_rolls", 0],
                ["dice_rolls", 1],
            ]
        )

        # Updated regex pattern for parsing actions with new bid format
        self.bid_pattern = re.compile(r"\[bid:\s*(\d+),\s*(\d+)\]", re.IGNORECASE)
        self.call_pattern = re.compile(r"\[call\]", re.IGNORECASE)

    def reset(
        self, seed: Optional[int] = None
    ) -> Optional[ta.Observations]:
        """
        Reset the Liar's Dice game to its initial state.

        Args:
            seed (Optional[int]): Seed for the random number generator to ensure reproducibility.

        Returns:
            Tuple[Dict[int, List[Tuple[int, str]]], Dict[str, Any]]:
                - Observations for each player as a dictionary.
                - Additional information, including all dice rolls.
        """
        if seed is not None:
            random.seed(seed)
        else:
            random.seed()

        # Each player rolls their dice
        game_state = {
            "current_bid": {"quantity": 0, "face_value": 0},
            "dice_rolls": {
                0: [random.randint(1, 6) for _ in range(self.num_dice)],
                1: [random.randint(1, 6) for _ in range(self.num_dice)],
            },
        }

        return self.state.reset(
            game_state=game_state,
            player_prompt_function=self._generate_player_prompt
        )

    def _generate_player_prompt(self, player_id: int, game_state: Dict[int, Any]) -> str:
        """
        Generate the initial prompt for a player.

        Args:
            player_id (int): The player's ID.

        Returns:
            str: The initial prompt for the player.
        """
        dice = game_state["dice_rolls"][player_id]
        prompt = (
            f"You are Player {player_id} in Liar's Dice.\n"
            f"You have rolled {self.num_dice} dice: {', '.join(map(str, dice))}.\n"
            "Players take turns making bids on the total quantity of a face value among all dice.\n"
            "On your turn, you can either make a higher bid or call the opponent's bluff.\n"
            "Actions:\n"
            "- To make a bid: '[Bid: <quantity>, <face_value>]', e.g., '[Bid: 3, 4]'\n"
            "- To call a bluff: '[Call]'\n"
            "If you call a bluff, all dice are revealed:\n"
            "- If the actual quantity of the face value is less than the bid, you win.\n"
            "- If the actual quantity meets or exceeds the bid, you lose.\n"
            f"The current bid is: Quantity = 0, Face Value = 0\n"
            "It's your turn. What is your action?"
        )
        return prompt

    def step(
        self,
        player_id: int,
        action: str,
    ) -> Tuple[
        Optional[Dict[int, str]],  # observations
        Optional[Dict[int, int]],  # reward
        bool,  # truncated
        bool,  # terminated
        Dict[str, Any],  # info
    ]:
        """
        Process the player's action.

        Args:
            player_id (int): The player's ID (0 or 1).
            action (str): The player's action.

        Returns:
            tuple: (observations, rewards, truncated, terminated, info)
        """
        # Check the player_id and action format
        self.state.check_action_format(
            action=action,
            player_id=player_id
        )


        # Update the observations and log the action
        self.state.add_observation(
            from_id=player_id,
            to_id=-1,  # Broadcast to all
            message=action,
            for_logging=True
        )

        # Check if the player is making a bid
        bid_match = self.bid_pattern.search(action)
        if bid_match:
            new_quantity = int(bid_match.group(1))
            new_face_value = int(bid_match.group(2))

            # Validate the bid
            current_bid = self.state.game_state["current_bid"]
            if self._is_valid_bid(new_quantity, new_face_value, current_bid):
                # Update the current bid
                self.state.game_state["current_bid"] = {
                    "quantity": new_quantity,
                    "face_value": new_face_value
                }
                # Log the bid update
                self.state.add_observation(
                    from_id=ta.GAME_ID,
                    to_id=-1,  # Broadcast to all
                    message=f"Player {player_id} increases the bid to Quantity = {new_quantity}, Face Value = {new_face_value}",
                    for_logging=True
                )

            else:
                # Invalid bid
                self.state.set_invalid_move(
                    player_ids=[player_id],
                    reasons=[f"Invalid bid by Player {player_id}: Quantity = {new_quantity}, Face Value = {new_face_value}."]
                )

        # Check if the player is calling a bluff
        elif self.call_pattern.search(action):
            # check if a call was made in the very first turn
            if self.state.turn == 0:
                self.state.set_invalid_move(
                    player_ids=[player_id],
                    reasons=[f"Player {player_id} tried to call without a bid having been made by anybody."]
                )
            else:
                current_bid = self.state.game_state["current_bid"]
                total_quantity = sum(
                    dice.count(current_bid["face_value"])
                    for dice in self.state.game_state["dice_rolls"].values()
                )
                bid_quantity = current_bid["quantity"]

                # Reveal all dice (for testing, dice are already known)
                if total_quantity < bid_quantity:
                    # Challenger wins
                    self.state.set_winners(
                        player_ids=[player_id],
                        reason=(
                            f"Bluff called by Player {player_id}. "
                            f"Actual quantity of face value {current_bid['face_value']} is {total_quantity}, "
                            f"which is less than the bid ({bid_quantity}). "
                            f"Player {player_id} wins."
                        )
                    )

                else:
                    # Challenger loses
                    self.state.set_winners(
                        player_ids=[1-player_id],
                        reason=(
                            f"Bluff called by Player {player_id}. "
                            f"Actual quantity of face value {current_bid['face_value']} is {total_quantity}, "
                            f"which meets or exceeds the bid ({bid_quantity}). "
                            f"Player {player_id} loses."
                        )
                    )

        else:
            # Invalid action
            self.state.set_invalid_move(
                player_ids=[player_id],
                reasons=[f"Invalid action by Player {player_id}: '{action}'. Must use '[Bid: <quantity>, <face_value>]' or '[Call]'."]
            )

        return self.state.step()

    def _is_valid_bid(self, new_quantity: int, new_face_value: int, current_bid: Dict[str, int]) -> bool:
        """
        Validate whether the new bid is higher than the current bid.

        Args:
            new_quantity (int): Quantity in the new bid.
            new_face_value (int): Face value in the new bid.
            current_bid (Dict[str, int]): Current bid details.

        Returns:
            bool: True if the bid is valid, False otherwise.
        """
        if new_quantity < current_bid["quantity"]:
            return False
        if new_face_value < current_bid["face_value"]:
            return False
        if new_quantity == current_bid["quantity"] and new_face_value <= current_bid["face_value"]:
            return False
        if new_face_value == current_bid["face_value"] and new_quantity <= current_bid["quantity"]:
            return False 
        if not (1 <= new_face_value <= 6):
            return False
        return True

    def render(self):
        """
        Render the current game state to the console.
        """
        current_bid = self.state.game_state["current_bid"]
        print(f"Turn: {self.state.game_state.get('turn', 'N/A')}")
        print(f"Current Bid: Quantity = {current_bid['quantity']}, Face Value = {current_bid['face_value']}")
        print("\nGame Logs:")
        for sender_id, message in self.state.game_state.get("logs", []):
            if sender_id == "GAME":
                print(f"[GAME]: {message}")
            else:
                print(f"Player {sender_id}: {message}")
        print("\n")
