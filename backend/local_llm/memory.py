# ==========================================
# Enterprise Conversation Memory
# ==========================================

from collections import deque


# ==========================================
# Memory Configuration
# ==========================================

MAX_HISTORY = 10


# ==========================================
# Conversation Memory
# ==========================================

class ConversationMemory:

    def __init__(self):

        self.history = deque(maxlen=MAX_HISTORY)

    # ======================================
    # Add User + Assistant Conversation
    # ======================================

    def add_exchange(self, question, answer):

        self.history.append({

            "question": question,

            "answer": answer

        })

    # ======================================
    # Get Conversation Context
    # ======================================

    def get_context(self):

        if not self.history:

            return ""

        context = ""

        for chat in self.history:

            context += f"""

User:
{chat['question']}

Assistant:
{chat['answer']}

"""

        return context.strip()

    # ======================================
    # Clear Memory
    # ======================================

    def clear(self):

        self.history.clear()

    # ======================================
    # Total Conversations
    # ======================================

    def size(self):

        return len(self.history)


# ==========================================
# Global Memory Instance
# ==========================================

memory = ConversationMemory()


# ==========================================
# Debug
# ==========================================

if __name__ == "__main__":

    memory.add_exchange(

        "Show my applications",

        "Microsoft Edge, Microsoft Word"

    )

    memory.add_exchange(

        "Which one is from Microsoft?",

        "Microsoft Edge and Microsoft Word."

    )

    print(memory.get_context())